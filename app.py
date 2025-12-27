import streamlit as st
import os
import json
import uuid
import zipfile
from io import BytesIO
import pandas as pd
from PIL import Image
import base64
from datetime import datetime

# Try to import drawable canvas, fallback if not available
try:
    from streamlit_drawable_canvas import st_canvas
    CANVAS_AVAILABLE_INITIAL = True
except ImportError:
    CANVAS_AVAILABLE_INITIAL = False

# Constants
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
ANNOTATIONS_DIR = os.path.join(DATA_DIR, "annotations")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(ANNOTATIONS_DIR, exist_ok=True)

# Helper functions
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

def load_projects():
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_projects(projects):
    with open(PROJECTS_FILE, 'w') as f:
        json.dump(projects, f)

# Initialize session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_type' not in st.session_state:
    st.session_state.user_type = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'canvas_enabled' not in st.session_state:
    st.session_state.canvas_enabled = CANVAS_AVAILABLE_INITIAL

def logout():
    st.session_state.logged_in = False
    st.session_state.user_type = None
    st.session_state.username = None
    st.rerun()

def main():
    st.title("Annotation Tool")

    if not st.session_state.logged_in:
        login_page()
    else:
        if st.session_state.user_type == 'admin':
            admin_page()
        elif st.session_state.user_type == 'user':
            user_page()

def login_page():
    st.header("Login")
    user_type = st.selectbox("Select User Type", ["user", "admin"])
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        users = load_users()
        if user_type == 'admin' and username == 'admin' and password == 'admin':
            st.session_state.logged_in = True
            st.session_state.user_type = 'admin'
            st.session_state.username = username
            st.rerun()
        elif user_type == 'user' and username in users and users[username]['password'] == password:
            st.session_state.logged_in = True
            st.session_state.user_type = 'user'
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Invalid credentials")

def admin_page():
    st.sidebar.button("Logout", on_click=logout)
    st.header("Admin Panel")
    menu = st.sidebar.selectbox("Menu", ["Create Project", "Add User", "Manage Projects", "View Users"])
    
    if menu == "Create Project":
        create_project()
    elif menu == "Add User":
        add_user()
    elif menu == "Manage Projects":
        manage_projects()
    elif menu == "View Users":
        view_users()

def user_page():
    st.sidebar.button("Logout", on_click=logout)
    st.header("User Panel")
    projects = load_projects()
    accessible_projects = [p for p in projects if st.session_state.username in projects[p]['access_users']]
    
    if not accessible_projects:
        st.write("No accessible projects")
        return
    
    selected_project = st.selectbox("Select Project", accessible_projects)
    project = projects[selected_project]
    
    assigned_images = project['assignments'].get(st.session_state.username, [])
    if not assigned_images:
        st.info("No assigned images")
        return
    
    # Group images by date
    images_by_date = {}
    for img_dict in project['images']:
        if img_dict['id'] in assigned_images:
            date = img_dict['date']
            images_by_date.setdefault(date, []).append(img_dict['id'])
    
    for date in sorted(images_by_date.keys(), reverse=True):
        st.subheader(f"Images uploaded on {date}")
        for img_id in images_by_date[date]:
            img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
            if os.path.exists(img_path):
                img = Image.open(img_path)
                
                # Option 1: Drawing Canvas
                if st.session_state.canvas_enabled:
                    try:
                        class_name = st.selectbox(f"Select Class for {img_id}", project['product_list'], key=f"class_{img_id}")
                        
                        canvas_result = st_canvas(
                            fill_color="rgba(255, 165, 0, 0.3)",
                            stroke_width=2,
                            stroke_color="#000000",
                            background_image=img,
                            update_streamlit=True,
                            height=img.height,
                            width=img.width,
                            drawing_mode="rect",
                            key=f"canvas_{img_id}",
                        )
                        
                        if st.button(f"Save Annotations for {img_id}", key=f"save_{img_id}"):
                            if canvas_result.json_data:
                                objects = canvas_result.json_data["objects"]
                                annotations = []
                                for obj in objects:
                                    if obj["type"] == "rect":
                                        # Normalize coordinates
                                        left, top = obj["left"] / img.width, obj["top"] / img.height
                                        w, h = obj["width"] / img.width, obj["height"] / img.height
                                        annotations.append({
                                            'class': class_name,
                                            'bbox': [left + w/2, top + h/2, w, h]
                                        })
                                project['annotations'].setdefault(img_id, {})[st.session_state.username] = annotations
                                save_projects(projects)
                                st.success("Saved!")
                    except Exception as e:
                        st.error(f"Canvas error: {e}")
                        st.session_state.canvas_enabled = False
                        st.rerun()

                # Option 2: Fallback Sliders
                else:
                    st.image(img)
                    class_name = st.selectbox(f"Class for {img_id}", project['product_list'], key=f"class_{img_id}")
                    x = st.slider(f"X center", 0.0, 1.0, 0.5, key=f"x_{img_id}")
                    y = st.slider(f"Y center", 0.0, 1.0, 0.5, key=f"y_{img_id}")
                    w = st.slider(f"Width", 0.0, 1.0, 0.1, key=f"w_{img_id}")
                    h = st.slider(f"Height", 0.0, 1.0, 0.1, key=f"h_{img_id}")
                    
                    if st.button(f"Add Annotation", key=f"add_{img_id}"):
                        project['annotations'].setdefault(img_id, {}).setdefault(st.session_state.username, []).append({
                            'class': class_name, 'bbox': [x, y, w, h]
                        })
                        save_projects(projects)
                        st.success("Added!")

# --- ADMIN FUNCTIONS (TRUNCATED FOR BREVITY BUT KEPT LOGIC) ---
def create_project():
    st.subheader("Create Project")
    project_name = st.text_input("Project Name")
    upload_option = st.radio("How to add products?", ["Manual Entry", "Upload Excel/CSV"])
    product_list = []
    
    if upload_option == "Manual Entry":
        products_text = st.text_area("Product List (comma separated)")
        product_list = [p.strip() for p in products_text.split(',') if p.strip()]
    elif upload_option == "Upload Excel/CSV":
        uploaded_file = st.file_uploader("Upload", type=['xlsx', 'csv'])
        if uploaded_file:
            df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            product_list = [str(p).strip() for p in df.iloc[:, 0].dropna().tolist()]

    if st.button("Create") and project_name:
        projects = load_projects()
        projects[project_name] = {'product_list': product_list, 'images': [], 'access_users': [], 'assignments': {}, 'annotations': {}}
        save_projects(projects)
        st.success("Project created")

def add_user():
    st.subheader("Add User")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Add"):
        users = load_users()
        users[username] = {'password': password}
        save_users(users)
        st.success("User added")

def manage_projects():
    projects = load_projects()
    if not projects: return st.write("No projects")
    
    selected_project = st.selectbox("Select Project", list(projects.keys()))
    project = projects[selected_project]
    
    # Upload
    uploaded_files = st.file_uploader("Upload Images", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    selected_date = st.date_input("Select Upload Date", value=datetime.now().date())
    if uploaded_files and st.button("Upload"):
        for file in uploaded_files:
            img_id = str(uuid.uuid4())
            with open(os.path.join(IMAGES_DIR, f"{img_id}.png"), 'wb') as f:
                f.write(file.getvalue())
            project['images'].append({'id': img_id, 'date': selected_date.strftime("%Y-%m-%d")})
        save_projects(projects)
        st.rerun()

    # User access
    new_user = st.text_input("Add User Access")
    if st.button("Add Access"):
        users = load_users()
        if new_user in users and new_user not in project['access_users']:
            project['access_users'].append(new_user)
            save_projects(projects)
            st.success("Access added")

    # Assignment
    if project['access_users']:
        user = st.selectbox("Assign to User", project['access_users'])
        avail = [img['id'] for img in project['images'] if img['id'] not in project['assignments'].get(user, [])]
        selected = st.multiselect("Select Images", avail)
        if st.button("Assign"):
            project['assignments'].setdefault(user, []).extend(selected)
            save_projects(projects)
            st.rerun()

    # Download
    if st.button("Download YOLO"):
        download_yolo(selected_project, project)

def view_users():
    users = load_users()
    for u, d in users.items(): st.write(f"User: {u} | Pwd: {d['password']}")

def download_yolo(project_name, project):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for img_dict in project['images']:
            img_id = img_dict['id']
            img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
            if os.path.exists(img_path):
                zip_file.write(img_path, f"images/{img_id}.png")
            
            if img_id in project['annotations']:
                txt_content = ""
                # Combine annotations from all users for this image
                for user, anns in project['annotations'][img_id].items():
                    for ann in anns:
                        class_id = project['product_list'].index(ann['class'])
                        x, y, w, h = ann['bbox']
                        txt_content += f"{class_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n"
                zip_file.writestr(f"labels/{img_id}.txt", txt_content)
    
    zip_buffer.seek(0)
    st.download_button("Download ZIP", zip_buffer, f"{project_name}_yolo.zip", "application/zip")

if __name__ == "__main__":
    main()
