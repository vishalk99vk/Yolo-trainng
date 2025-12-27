import streamlit as st
import os, json, uuid, zipfile
from io import BytesIO
import pandas as pd
from PIL import Image

# --- 1. SETUP DIRECTORIES ---
DATA_DIR = "data"
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

for d in [DATA_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

def load_json(f):
    if os.path.exists(f):
        try:
            with open(f, 'r') as file: return json.load(file)
        except: return {}
    return {}

def save_json(f, d):
    with open(f, 'w') as file: json.dump(d, file)

# --- 2. MAIN NAVIGATION ---
def main():
    st.set_page_config(page_title="YOLO Annotator Final", layout="wide")
    
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        st.title("🎯 YOLO Labeling System")
        with st.form("login_form"):
            u_name = st.text_input("Username")
            u_pass = st.text_input("Password", type="password")
            if st.form_submit_button("Sign In"):
                if u_name == "admin" and u_pass == "admin":
                    st.session_state.update({"logged_in": True, "user_type": "admin", "username": "admin"})
                    st.rerun()
                else:
                    users = load_json(USERS_FILE)
                    if u_name in users and users[u_name]['password'] == u_pass:
                        st.session_state.update({"logged_in": True, "user_type": "user", "username": u_name})
                        st.rerun()
                    else: st.error("Invalid Credentials")
    else:
        if st.session_state.user_type == "admin":
            admin_ui()
        else:
            user_ui()

# --- 3. ADMIN INTERFACE ---
def admin_ui():
    st.sidebar.title("Admin Panel")
    if st.sidebar.button("Logout"): 
        st.session_state.clear()
        st.rerun()
    
    projs = load_json(PROJECTS_FILE)
    users_data = load_json(USERS_FILE)
    
    tab1, tab2, tab3 = st.tabs(["Projects", "Users", "Export"])
    
    with tab1:
        p_name = st.text_input("New Project Name")
        p_file = st.file_uploader("Product List (CSV/XLSX)", type=['csv', 'xlsx'])
        if st.button("Create Project") and p_name and p_file:
            df = pd.read_csv(p_file) if p_file.name.endswith('.csv') else pd.read_excel(p_file)
            p_list = [str(x).strip() for x in df.iloc[:,0].dropna().tolist()]
            projs[p_name] = {'product_list': p_list, 'images': [], 'assignments': {}, 'annotations': {}, 'statuses': {}}
            save_json(PROJECTS_FILE, projs)
            st.success("Project Created!")

        st.divider()
        if projs:
            sel_p = st.selectbox("Select Project to add Images", list(projs.keys()))
            up = st.file_uploader("Upload Images", accept_multiple_files=True)
            if up and st.button("Upload"):
                for f in up:
                    id = str(uuid.uuid4())
                    Image.open(f).convert("RGB").save(os.path.join(IMAGES_DIR, f"{id}.png"))
                    projs[sel_p]['images'].append({'id': id})
                save_json(PROJECTS_FILE, projs)
                st.success("Images Uploaded!")

    with tab2:
        u_new = st.text_input("Worker Username")
        p_new = st.text_input("Worker Password")
        if st.button("Add User") and u_new and p_new:
            users_data[u_new] = {"password": p_new}
            save_json(USERS_FILE, users_data)
            st.success("User Added!")
        
        st.divider()
        if projs and users_data:
            p_assign = st.selectbox("Assign to Project", list(projs.keys()))
            u_assign = st.selectbox("Select Worker", list(users_data.keys()))
            if st.button("Assign All Images"):
                projs[p_assign]['assignments'][u_assign] = [i['id'] for i in projs[p_assign]['images']]
                save_json(PROJECTS_FILE, projs)
                st.success("Assigned!")

    with tab3:
        if projs:
            e_p = st.selectbox("Export Project", list(projs.keys()))
            if st.button("Download YOLO Dataset"):
                download_yolo(e_p, projs[e_p])

# --- 4. USER INTERFACE (FIXED VISIBILITY) ---
def user_ui():
    from streamlit_drawable_canvas import st_canvas
    st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
    
    projs = load_json(PROJECTS_FILE)
    active_p = None
    for n, p in projs.items():
        if st.session_state.username in p.get('assignments', {}):
            active_p = n
            break
            
    if not active_p:
        st.info("No tasks assigned yet.")
        return

    p = projs[active_p]
    my_tasks = p['assignments'][st.session_state.username]
    pending = [i for i in my_tasks if p['statuses'].get(i) != "Done"]

    if not pending:
        st.success("🎉 All assignments completed!")
        return

    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")

    # Load and force RGB
    raw_img = Image.open(img_path).convert("RGB")
    
    # Calculate visible dimensions (Max 800px height)
    h = 600
    w = int(h * (raw_img.width / raw_img.height))
    if w > 900: 
        w = 900
        h = int(w * (raw_img.height / raw_img.width))
    
    display_img = raw_img.resize((w, h), Image.Resampling.LANCZOS)

    col1, col2 = st.columns([1, 4])
    with col1:
        st.subheader("Tagging")
        sel_cls = st.selectbox("Select Product", p['product_list'])
        if st.button("💾 Save & Next", use_container_width=True):
            st.session_state["submit"] = True

    with col2:
        # The key canvas_{img_id} is CRITICAL. It forces a redraw for every new image.
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=2,
            stroke_color="#FF0000",
            background_image=display_img,
            background_color="#000000",
            height=h,
            width=w,
            drawing_mode="rect",
            key=f"canvas_{img_id}",
            update_freq=500
        )

    if st.session_state.get("submit"):
        if canvas_result.json_data and canvas_result.json_data["objects"]:
            objs = canvas_result.json_data["objects"]
            anns = []
            for o in objs:
                # Normalizing to YOLO format (0.0 to 1.0)
                wn, hn = o["width"]/w, o["height"]/h
                xc, yc = (o["left"]/w) + (wn/2), (o["top"]/h) + (hn/2)
                anns.append({"class": sel_cls, "bbox": [xc, yc, wn, hn]})
            
            p['annotations'][img_id] = anns
            p['statuses'][img_id] = "Done"
            save_json(PROJECTS_FILE, projs)
            st.session_state["submit"] = False
            st.rerun()
        else:
            st.warning("Please draw at least one box.")
            st.session_state["submit"] = False

# --- 5. EXPORT LOGIC ---
def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        # Create Classes File
        z.writestr("classes.txt", "\n".join(p['product_list']))
        
        for iid, anns in p['annotations'].items():
            img_p = os.path.join(IMAGES_DIR, f"{iid}.png")
            if os.path.exists(img_p):
                z.write(img_p, f"images/{iid}.png")
                lbl = ""
                for a in anns:
                    idx = p['product_list'].index(a['class'])
                    lbl += f"{idx} {' '.join([f'{v:.6f}' for v in a['bbox']])}\n"
                z.writestr(f"labels/{iid}.txt", lbl)
    
    st.download_button("Click to Download ZIP", buf.getvalue(), f"{name}_dataset.zip")

if __name__ == "__main__":
    main()
