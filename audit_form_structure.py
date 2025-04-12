import streamlit as st
st.set_page_config(page_title="Hotel Audit App", layout="wide")  # Must be the first Streamlit command

import os
import uuid
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from fpdf import FPDF
from pathlib import Path
import pandas as pd
from io import BytesIO

# --- Helper Function for Rerun ---
def rerun():
    """
    Attempts to re-run the Streamlit script. If st.experimental_rerun() is not available,
    logs a warning.
    """
    try:
        st.experimental_rerun()
    except AttributeError:
        logging.warning("st.experimental_rerun() is not available. Please upgrade Streamlit for auto-rerunning functionality.")

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Constants ---
GENERAL_CATEGORIES = [
    "Facade & Structure", "Main Lobby", "Corridors & Hallways", "Public Toilets",
    "Spa & Wellness", "Fitness Center", "Swimming Pools",
    "Landscaping & Outdoor", "Parking & Entry"
]

RATING_OPTIONS = [
    "1 - Needs to be changed due to age-related factors",
    "2 - Needs to be changed to match competing hotels",
    "3 - Not applicable",
    "4 - No action required"
]

# --- Directory Creation ---
try:
    Path("audits").mkdir(exist_ok=True)
    Path("photos").mkdir(exist_ok=True)
except Exception as e:
    logging.error("Error creating directories: %s", e)
    st.error("Could not create necessary directories. Check folder permissions.")

# --- Data Models ---
class ChecklistItem:
    """
    Data model for a single audit checklist item.
    """
    def __init__(self, section: str, item: str, note: str = "Provide observation or reason"):
        self.section = section
        self.item = item
        self.note = note

class AuditResponse:
    """
    Represents a response to a single checklist item during the audit.
    """
    def __init__(
        self, 
        checklist_item: ChecklistItem, 
        rating: str, 
        comment: str, 
        photo_file: Optional[str], 
        context: Optional[str] = None
    ):
        self.checklist_item = checklist_item
        self.rating = rating
        self.comment = comment
        self.photo_file = photo_file
        self.context = context
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Converts the audit response to a dictionary for JSON serialization."""
        return {
            "context": self.context,
            "section": self.checklist_item.section,
            "item": self.checklist_item.item,
            "note": self.checklist_item.note,
            "rating": self.rating,
            "comment": self.comment,
            "photo_file": self.photo_file,
            "timestamp": self.timestamp.isoformat()
        }

    @property
    def rating_description(self) -> str:
        """Extracts and returns the descriptive part of the rating."""
        return self.rating.split(" - ", 1)[1] if " - " in self.rating else self.rating

class AuditSession:
    """
    Encapsulates an entire audit session.
    """
    def __init__(self, hotel_info: dict, auditor_name: str):
        safe_hotel_name = hotel_info.get("name", "Hotel").replace(' ', '_')
        self.session_id = f"{safe_hotel_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.hotel_info = hotel_info
        self.auditor_name = auditor_name
        self.timestamp = datetime.utcnow()
        self.responses: List[AuditResponse] = []

    def add_response(self, response: AuditResponse):
        """Adds a new audit response to the session."""
        self.responses.append(response)

    def summary(self) -> Dict[str, Any]:
        """Returns a summary of the audit session."""
        return {
            "session_id": self.session_id,
            "hotel": self.hotel_info,
            "auditor": self.auditor_name,
            "responses_count": len(self.responses),
            "timestamp": self.timestamp.isoformat()
        }

    def to_dict(self) -> Dict[str, Any]:
        """Converts the entire audit session into a dictionary."""
        return {
            "session_id": self.session_id,
            "hotel_info": self.hotel_info,
            "auditor_name": self.auditor_name,
            "timestamp": self.timestamp.isoformat(),
            "responses": [r.to_dict() for r in self.responses]
        }

    def save_to_file(self) -> str:
        """
        Saves the audit session as a JSON file in the 'audits' directory.
        Returns the file path.
        """
        file_path = f"audits/{self.session_id}.json"
        try:
            with open(file_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            logging.info("Session saved successfully to %s", file_path)
        except Exception as e:
            logging.error("Error saving session file: %s", e)
            st.error("Error saving session data.")
        return file_path

    def get_responses_by_section(self) -> Dict[str, List[AuditResponse]]:
        """Groups responses by their audit section."""
        sections = {}
        for response in self.responses:
            section = response.checklist_item.section
            if section not in sections:
                sections[section] = []
            sections[section].append(response)
        return sections

# --- Utility Functions ---
def display_photo_if_exists(photo_path: Optional[str]) -> None:
    """
    Displays an image from the given path if it exists.
    """
    if photo_path and os.path.exists(photo_path):
        st.image(photo_path, caption="Uploaded Photo", use_column_width=True)

def save_uploaded_photo(uploaded_file) -> Optional[str]:
    """
    Saves an uploaded photo to the 'photos' directory and returns its file path.
    Includes error handling for file operations.
    """
    if uploaded_file:
        photo_id = str(uuid.uuid4())
        photo_filename = f"{photo_id}_{uploaded_file.name}"
        photo_path = os.path.join("photos", photo_filename)
        try:
            with open(photo_path, "wb") as f:
                f.write(uploaded_file.read())
            logging.info("Saved photo to %s", photo_path)
            return photo_path
        except Exception as e:
            logging.error("Error saving uploaded photo: %s", e)
            st.error("Error saving the uploaded photo.")
            return None
    return None

def generate_excel_data(session: AuditSession) -> pd.DataFrame:
    """
    Converts audit session data into an Excel-ready DataFrame.
    """
    data = []
    for response in session.responses:
        rating_num = response.rating.split(" - ")[0]
        rating_desc = next(
            (opt for opt in RATING_OPTIONS if opt.startswith(rating_num)),
            response.rating
        )
        data.append({
            "Section": response.checklist_item.section,
            "Item": response.checklist_item.item,
            "Rating": rating_desc,
            "Comment": response.comment,
            "Context": response.context or "General",
            "Photo": "Yes" if response.photo_file else "No",
            "Timestamp": response.timestamp.strftime('%Y-%m-%d %H:%M')
        })
    return pd.DataFrame(data)

def create_question_card(item: str, section: str, existing_response: Optional[AuditResponse] = None, context: Optional[str] = None):
    """
    Creates a UI card for an audit checklist item with input fields,
    and returns the state of the action buttons and user inputs.
    """
    card = st.container()
    with card:
        if existing_response:
            st.markdown(
                """
                <style>
                    div[data-testid="stVerticalBlock"] {
                        background-color: #f0f2f6;
                        padding: 10px;
                        border-radius: 5px;
                        margin-bottom: 10px;
                    }
                </style>
                """,
                unsafe_allow_html=True
            )
        st.markdown(f"**{item}**")
        default_rating = existing_response.rating if existing_response else RATING_OPTIONS[0]
        default_comment = existing_response.comment if existing_response else ""
        unique_key = f"{section}_{item}_{context or 'general'}"
        rating = st.selectbox(
            "Rating", 
            RATING_OPTIONS, 
            index=RATING_OPTIONS.index(default_rating) if default_rating in RATING_OPTIONS else 0,
            key=f"rating_{unique_key}"
        )
        comment = st.text_area("Comment", value=default_comment, key=f"comment_{unique_key}")
        photo = st.file_uploader("Upload Photo", type=["jpg", "png", "jpeg"], key=f"photo_{unique_key}")
        if existing_response and existing_response.photo_file:
            display_photo_if_exists(existing_response.photo_file)
        col1, col2 = st.columns([1, 4])
        with col1:
            save_pressed = st.button("Save Response", key=f"save_{unique_key}")
        with col2:
            clear_pressed = st.button("Clear Response", key=f"clear_{unique_key}", disabled=not existing_response)
        return save_pressed, clear_pressed, rating, comment, photo

def generate_pdf_report(session: AuditSession) -> str:
    """
    Generates a PDF report from the audit session data using FPDF,
    saves the PDF to the audits directory, and returns the file path.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Hotel Audit Report", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Hotel Information", ln=True)
    pdf.set_font("Arial", size=11)
    hotel_info = session.hotel_info
    pdf.cell(0, 8, txt=f"Hotel Name: {hotel_info.get('name', 'N/A')}", ln=True)
    pdf.cell(0, 8, txt=f"Location: {hotel_info.get('city', 'N/A')}, {hotel_info.get('country', 'N/A')}", ln=True)
    pdf.cell(0, 8, txt=f"Year Opened: {hotel_info.get('year_opened', 'N/A')}", ln=True)
    pdf.cell(0, 8, txt=f"Floors: {hotel_info.get('floors', 'N/A')}", ln=True)
    pdf.cell(0, 8, txt=f"Total Rooms: {hotel_info.get('total_rooms', 'N/A')}", ln=True)
    pdf.ln(5)
    pdf.cell(0, 8, txt=f"Auditor: {session.auditor_name}", ln=True)
    pdf.cell(0, 8, txt=f"Date: {session.timestamp.strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Audit Findings", ln=True)
    pdf.set_font("Arial", size=11)
    sections = session.get_responses_by_section()
    for section, responses in sections.items():
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 8, txt=f"Section: {section}", ln=True)
        pdf.set_font("Arial", size=10)
        for idx, r in enumerate(responses, 1):
            context_info = f" ({r.context})" if r.context else ""
            pdf.multi_cell(0, 6, txt=f"{idx}. Item: {r.checklist_item.item}{context_info}")
            pdf.multi_cell(0, 6, txt=f"Rating: {r.rating_description}")
            pdf.multi_cell(0, 6, txt=f"Comment: {r.comment}")
            pdf.ln(2)
    file_path = f"audits/{session.session_id}.pdf"
    try:
        pdf.output(file_path)
        logging.info("PDF report generated at %s", file_path)
    except Exception as e:
        logging.error("Error generating PDF report: %s", e)
        st.error("Failed to generate PDF report.")
    return file_path

@st.cache_data(show_spinner=False)
def load_master_checklist() -> Dict[str, List[str]]:
    """
    Loads the master checklist from a JSON file.
    Falls back to default categories if the file is not found or an error occurs.
    """
    try:
        with open("master_checklist_template.json") as f:
            checklist = json.load(f)
        return checklist
    except FileNotFoundError:
        st.error("Master checklist file not found. Using default categories.")
        return {category: [] for category in GENERAL_CATEGORIES + ["F&B Outlets", "Ballrooms & Meeting Rooms", "Guestroom"]}
    except Exception as e:
        logging.error("Error loading master checklist: %s", e)
        st.error("Unexpected error loading checklist.")
        return {}

# Load master checklist once
checklist_dict = load_master_checklist()

# --- Audit Section Functions ---
def general_section_audit(session: AuditSession) -> None:
    """
    Handles audit responses for a general section.
    Allows multiple responses per checklist item.
    """
    selected_section = st.session_state['selected_general_section']
    # Gather all responses for the selected section
    section_responses = [r for r in session.responses if r.checklist_item.section == selected_section]
    if selected_section in checklist_dict:
        with st.expander(f"Audit Items for {selected_section}", expanded=True):
            for item in checklist_dict[selected_section]:
                # Get all responses for this checklist item
                existing_responses = [r for r in section_responses if r.checklist_item.item == item]
                latest_response = existing_responses[-1] if existing_responses else None
                save_pressed, clear_pressed, rating, comment, photo = create_question_card(item, selected_section, latest_response)
                if save_pressed:
                    photo_path = latest_response.photo_file if latest_response else None
                    if photo:
                        photo_path = save_uploaded_photo(photo)
                    # Append the new response without removing the earlier ones
                    session.add_response(
                        AuditResponse(
                            ChecklistItem(selected_section, item),
                            rating,
                            comment,
                            photo_path
                        )
                    )
                    st.success(f"Saved response for: {item}")
                    rerun()
                if clear_pressed and existing_responses:
                    # Clear all responses for this checklist item
                    for r in existing_responses:
                        session.responses.remove(r)
                    st.warning(f"Cleared responses for: {item}")
                    rerun()

def specific_section_audit(session: AuditSession, section_type: str, section_name: str) -> None:
    """
    Handles audit responses for specialized sections (F&B, Meeting Room, Guestroom).
    Allows multiple responses per checklist item.
    """
    checklist_key = {
        "F&B": "F&B Outlets",
        "Meeting Room": "Ballrooms & Meeting Rooms",
        "Guestroom": "Guestroom"
    }.get(section_type, "")
    
    if checklist_key in checklist_dict:
        section_responses = [r for r in session.responses if r.context == section_name and r.checklist_item.section == checklist_key]
        with st.expander(f"Audit Items for {section_type}: {section_name}", expanded=True):
            for item in checklist_dict[checklist_key]:
                existing_responses = [r for r in section_responses if r.checklist_item.item == item]
                latest_response = existing_responses[-1] if existing_responses else None
                save_pressed, clear_pressed, rating, comment, photo = create_question_card(item, checklist_key, latest_response, section_name)
                if save_pressed:
                    photo_path = latest_response.photo_file if latest_response else None
                    if photo:
                        photo_path = save_uploaded_photo(photo)
                    session.add_response(
                        AuditResponse(
                            ChecklistItem(checklist_key, item),
                            rating,
                            comment,
                            photo_path,
                            context=section_name
                        )
                    )
                    st.success(f"Saved response for: {item}")
                    rerun()
                if clear_pressed and existing_responses:
                    for r in existing_responses:
                        session.responses.remove(r)
                    st.warning(f"Cleared responses for: {item}")
                    rerun()

# --- Main Application ---
def main():
    """
    Main entry point for the Hotel Audit App.
    Sets up the Streamlit layout, handles session initialization,
    gathers hotel and auditor details, and routes to the appropriate audit sections.
    """
    st.title("Hotel Audit App")
    
    # Initialize session state if necessary
    if 'session' not in st.session_state:
        st.session_state['session'] = None
    if 'selected_section' not in st.session_state:
        st.session_state['selected_section'] = "General Sections"
    if 'selected_general_section' not in st.session_state:
        st.session_state['selected_general_section'] = GENERAL_CATEGORIES[0]
    
    st.sidebar.title("Audit Navigation")
    
    # Session Initialization: Collect Hotel Information
    if st.session_state['session'] is None:
        st.header("Step 1: Hotel Information")
        hotel_name = st.text_input("Hotel Name", key="hotel_name")
        city = st.text_input("City", key="city")
        country = st.text_input("Country", key="country")
        year_opened = st.number_input("Year Opened", min_value=1800, max_value=datetime.now().year, value=2000, step=1, key="year_opened")
        num_floors = st.number_input("Number of Floors", min_value=1, max_value=100, value=1, step=1, key="num_floors")
        total_rooms = st.number_input("Total Guestrooms", min_value=1, max_value=1000, value=50, step=1, key="total_rooms")
        
        st.subheader("F&B Outlets")
        fnb_count = st.number_input("Number of F&B Outlets", min_value=0, max_value=20, step=1, key="fnb_count")
        fnb_outlets = [st.text_input(f"F&B Outlet #{i+1}", key=f"fnb_{i}") for i in range(int(fnb_count))]
        
        st.subheader("Meeting Rooms")
        meeting_count = st.number_input("Number of Meeting Rooms", min_value=0, max_value=20, step=1, key="meeting_count")
        meeting_rooms = [st.text_input(f"Meeting Room #{i+1}", key=f"meeting_{i}") for i in range(int(meeting_count))]
        
        st.subheader("Guestroom Types")
        guestroom_count = st.number_input("Number of Guestroom Types", min_value=0, max_value=20, step=1, key="guestroom_count")
        guestroom_types = []
        for i in range(int(guestroom_count)):
            name = st.text_input(f"Guestroom Type #{i+1} Name", key=f"guestroom_{i}")
            size = st.text_input(f"Size (sqm) for {name}", key=f"guestroom_size_{i}")
            count = st.text_input(f"Number of Keys for {name}", key=f"guestroom_keys_{i}")
            guestroom_types.append({"name": name, "size": size, "keys": count})
        
        auditor_name = st.text_input("Auditor Name", key="auditor_name")
        
        if st.button("Start Audit"):
            if not hotel_name or not auditor_name:
                st.error("Hotel Name and Auditor Name are required fields")
                return
            hotel_info = {
                "name": hotel_name,
                "city": city,
                "country": country,
                "year_opened": year_opened,
                "floors": num_floors,
                "total_rooms": total_rooms,
                "fnb_outlets": fnb_outlets,
                "meeting_rooms": meeting_rooms,
                "guestroom_types": guestroom_types
            }
            st.session_state['session'] = AuditSession(hotel_info, auditor_name)
            logging.info("Started new audit session: %s", st.session_state['session'].session_id)
            rerun()
    else:
        session: AuditSession = st.session_state['session']
        st.sidebar.subheader("Audit Info")
        st.sidebar.write(f"Hotel: {session.hotel_info.get('name', 'N/A')}")
        st.sidebar.write(f"Auditor: {session.auditor_name}")
        st.sidebar.write(f"Started: {session.timestamp.strftime('%Y-%m-%d %H:%M')}")
        st.sidebar.write(f"Items Completed: {len(session.responses)}")
        
        if st.sidebar.button("New Audit"):
            st.session_state['session'] = None
            st.session_state['selected_section'] = "General Sections"
            rerun()
        
        st.sidebar.subheader("Select Section")
        section_options = (["General Sections"] +
                           [f"F&B: {x}" for x in session.hotel_info.get("fnb_outlets", []) if x.strip()] +
                           [f"Meeting Room: {x}" for x in session.hotel_info.get("meeting_rooms", []) if x.strip()] +
                           [f"Guestroom: {x['name']}" for x in session.hotel_info.get("guestroom_types", []) if x.get("name")])
        
        selected_section = st.sidebar.radio(
            "Choose Audit Section", 
            section_options,
            index=section_options.index(st.session_state['selected_section']) if st.session_state['selected_section'] in section_options else 0
        )
        st.session_state['selected_section'] = selected_section
        
        if selected_section == "General Sections":
            selected_general = st.sidebar.radio(
                "General Categories",
                GENERAL_CATEGORIES,
                index=GENERAL_CATEGORIES.index(st.session_state['selected_general_section']) if st.session_state['selected_general_section'] in GENERAL_CATEGORIES else 0
            )
            st.session_state['selected_general_section'] = selected_general
        
        if selected_section == "General Sections":
            general_section_audit(session)
        elif selected_section.startswith("F&B"):
            outlet_name = selected_section.split(": ", 1)[1]
            specific_section_audit(session, "F&B", outlet_name)
        elif selected_section.startswith("Meeting Room"):
            room_name = selected_section.split(": ", 1)[1]
            specific_section_audit(session, "Meeting Room", room_name)
        elif selected_section.startswith("Guestroom"):
            room_name = selected_section.split(": ", 1)[1]
            specific_section_audit(session, "Guestroom", room_name)
        
        st.sidebar.subheader("Reports & Export")
        if st.sidebar.button("Generate PDF Report"):
            with st.spinner("Generating PDF report..."):
                pdf_path = generate_pdf_report(session)
                try:
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    st.sidebar.download_button(
                        label="Download PDF Report",
                        data=pdf_bytes,
                        file_name=f"Hotel_Audit_{session.session_id}.pdf",
                        mime="application/pdf"
                    )
                except Exception as e:
                    logging.error("Error reading generated PDF: %s", e)
                    st.error("Failed to read the PDF report.")
        
        if st.sidebar.button("Export to Excel"):
            if 'session' not in st.session_state:
                st.sidebar.warning("No audit session found")
            else:
                df = generate_excel_data(st.session_state['session'])
                if not df.empty:
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False, sheet_name='Audit Results')
                        workbook = writer.book
                        worksheet = writer.sheets['Audit Results']
                        header_format = workbook.add_format({
                            'bold': True,
                            'bg_color': '#D7E4BC',
                            'border': 1
                        })
                        for col_num, value in enumerate(df.columns.values):
                            worksheet.write(0, col_num, value, header_format)
                            max_len = max(df[value].astype(str).map(len).max(), len(value)) + 2
                            worksheet.set_column(col_num, col_num, max_len)
                    st.sidebar.download_button(
                        label="⬇️ Download Excel File",
                        data=output.getvalue(),
                        file_name=f"hotel_audit_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.sidebar.warning("No audit data available to export")

if __name__ == "__main__":
    main()
