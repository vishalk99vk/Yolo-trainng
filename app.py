import streamlit as st
import os
import json
import uuid
import zipfile
from io import BytesIO
import pandas as pd
from PIL import Image
import base64

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

# Load data functions
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
if 'current_project' not in st.session_state:
    st.session_state.current_project = None
if 'current_image_index' not in st.session_state:
    st.session_state.current_image_index = 0

# Main app
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
        if user_type == 'admin' and username == 'admin' and password == 'admin':  # Hardcoded admin for simplicity
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
    st.header("Admin Panel")
    menu = st.sidebar.selectbox("Menu", ["Create Project", "Add User", "Manage Projects"])
    
    if menu == "Create Project":
        create_project()
    elif menu == "Add User":
        add_user()
    elif menu == "Manage Projects":
        manage_projects()

def create_project():
    st.subheader("Create Project")
    project_name = st.text_input("Project Name")
    
    # Option to upload Excel or enter manually
    upload_option = st.radio("How to add products?", ["Manual Entry", "Upload Excel/CSV"])
    product_list = []
    
    if upload_option == "Manual Entry":
        products_text = st.text_area("Product List (comma separated)")
        if products_text:
            product_list = [p.strip() for p in products_text.split(',') if p.strip()]
    elif upload_option == "Upload Excel/CSV":
        uploaded_file = st.file_uploader("Upload Excel or CSV file", type=['xlsx', 'xls', 'xlsm', 'xlsb', 'csv'])
        if uploaded_file:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            # Assume the first column has product names
            if not df.empty:
                product_list = df.iloc[:, 0].dropna().tolist()
                product_list = [str(p).strip() for p in product_list if str(p).strip()]
                st.write("Products from file:", product_list)
    
    if st.button("Create"):
        projects = load_projects()
        if project_name not in projects:
            projects[project_name] = {
                'product_list': product_list,
                'images': [],
                'access_users': [],
                'assignments': {},  # user: [image_ids]
                'annotations': {}  # image_id: {user: annotations}
            }
            save_projects(projects)
            st.success("Project created")
        else:
            st.error("Project already exists")

def add_user():
    st.subheader("Add User")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Add"):
        users = load_users()
        if username not in users:
            users[username] = {'password': password}
            save_users(users)
            st.success("User added")
        else:
            st.error("User already exists")

def manage_projects():
    projects = load_projects()
    project_names = list(projects.keys())
    if not project_names:
        st.write("No projects")
        return
    
    selected_project = st.selectbox("Select Project", project_names)
    project = projects[selected_project]
    
    st.subheader(f"Manage {selected_project}")
    
    # Add images
    uploaded_files = st.file_uploader("Upload Images", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    if uploaded_files:
        for file in uploaded_files:
            image_id = str(uuid.uuid4())
            image_path = os.path.join(IMAGES_DIR, f"{image_id}.png")
            with open(image_path, 'wb') as f:
                f.write(file.getvalue())
            project['images'].append(image_id)
        save_projects(projects)
        st.success("Images uploaded")
    
    # Product list
    st.write("Product List:", project['product_list'])
    
    # Assign access
    new_user = st.text_input("Add User Access")
    if st.button("Add Access"):
        if new_user not in project['access_users']:
            project['access_users'].append(new_user)
            save_projects(projects)
            st.success("Access added")
    
    # Assign data to users
    st.subheader("Assign Images to Users")
    users = project['access_users']
    if users:
        user = st.selectbox("Select User", users)
        available_images = [img for img in project['images'] if img not in project['assignments'].get(user, [])]
        selected_images = st.multiselect("Select Images", available_images)
        if st.button("Assign"):
            if user not in project['assignments']:
                project['assignments'][user] = []
            project['assignments'][user].extend(selected_images)
            save_projects(projects)
            st.success("Assigned")
    
    # View progress
    st.subheader("Progress")
    for user in users:
        assigned = len(project['assignments'].get(user, []))
        completed = 0
        for img in project['assignments'].get(user, []):
            if img in project['annotations'] and user in project['annotations'][img]:
                completed += 1
        st.write(f"{user}: {completed}/{assigned} completed")
    
    # Download YOLO
    if all(len(project['assignments'].get(u, [])) == sum(1 for img in project['assignments'].get(u, []) if img in project['annotations'] and u in project['annotations'][img]) for u in users):
        if st.button("Download YOLO"):
            download_yolo(selected_project, project)

def download_yolo(project_name, project):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        # Images
        for img_id in project['images']:
            img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
            zip_file.write(img_path, f"images/{img_id}.png")
        
        # Annotations
        for img_id in project['images']:
            if img_id in project['annotations']:
                for user, anns in project['annotations'][img_id].items():
                    txt_content = ""
                    for ann in anns:
                        class_id = project['product_list'].index(ann['class'])
                        x, y, w, h = ann['bbox']  # Assume normalized
                        txt_content += f"{class_id} {x} {y} {w} {h}\n"
                    zip_file.writestr(f"labels/{img_id}.txt", txt_content)
    
    zip_buffer.seek(0)
    st.download_button("Download ZIP", zip_buffer, f"{project_name}_yolo.zip", "application/zip")

def user_page():
    st.header("User Panel")
    projects = load_projects()
    accessible_projects = [p for p in projects if st.session_state.username in projects[p]['access_users']]
    
    if not accessible_projects:
        st.write("No accessible projects")
        return
    
    selected_project = st.selectbox("Select Project", accessible_projects)
    project = projects[selected_project]
    
    st.write("Product List:", project['product_list'])
    
    assigned_images = project['assignments'].get(st.session_state.username, [])
    if not assigned_images:
        st.write("No assigned images")
        return
    
    if st.session_state.current_project != selected_project:
        st.session_state.current_project = selected_project
        st.session_state.current_image_index = 0
    
    current_img_id = assigned_images[st.session_state.current_image_index]
    img_path = os.path.join(IMAGES_DIR, f"{current_img_id}.png")
    if os.path.exists(img_path):
        img = Image.open(img_path)
        st.image(img, caption=f"Image {st.session_state.current_image_index + 1}/{len(assigned_images)}")
        
        # Simple annotation input (for demo; in real app, use a proper annotation tool)
        class_name = st.selectbox("Class", project['product_list'])
        x = st.slider("X center", 0.0, 1.0, 0.5)
        y = st.slider("Y center", 0.0, 1.0, 0.5)
        w = st.slider("Width", 0.0, 1.0, 0.1)
        h = st.slider("Height", 0.0, 1.0, 0.1)
        
        if st.button("Add Annotation"):
            if current_img_id not in project['annotations']:
                project['annotations'][current_img_id] = {}
            if st.session_state.username not in project['annotations'][current_img_id]:
                project['annotations'][current_img_id][st.session_state.username] = []
            project['annotations'][current_img_id][st.session_state.username].append({
                'class': class_name,
                'bbox': [x, y, w, h]
            })
            save_projects(projects)
            st.success("Annotation added")
        
        if st.button("Complete Image"):
            # Mark as completed (already handled by presence in annotations)
            if st.session_state.current_image_index < len(assigned_images) - 1:
                st.session_state.current_image_index += 1
                st.rerun()
            else:
                st.success("All images completed")
        
        if st.session_state.current_image_index == len(assigned_images) - 1 and st.button("Send to Admin"):
            # Already completed
            st.success("Sent to admin")

if __name__ == "__main__":
    main()
