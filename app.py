import streamlit as st
import os
import json
import uuid
import zipfile
import base64
from io import BytesIO
import pandas as pd
from PIL import Image, ImageDraw
from datetime import datetime

# 1. Safe Import
try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS_LIB = True
except ImportError:
    HAS_CANVAS_LIB = False

# --- UTILITY TO CONVERT IMAGE FOR CANVAS ---
def get_image_base64(img):
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

# ... (Previous load_json / save_json logic stays the same) ...

# --- UPDATED USER PAGE ---
def user_page():
    st.sidebar.button("Logout", on_click=logout)
    projs = load_json(PROJECTS_FILE)
    my_projs = [n for n, p in projs.items() if st.session_state.username in p['access_users']]
    
    if not my_projs:
        st.info("Waiting for assignments...")
        return

    sel_p = st.selectbox("Select Project", my_projs)
    p = projs[sel_p]
    my_imgs = p['assignments'].get(st.session_state.username, [])
    pending = [i for i in my_imgs if p.get('statuses', {}).get(i, {}).get(st.session_state.username) != "Completed"]
    
    st.write(f"Task: {len(my_imgs) - len(pending)} / {len(my_imgs)} Completed")

    if not pending:
        st.success("All completed!")
        return

    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    if os.path.exists(img_path):
        img = Image.open(img_path)
        # FIX: Convert image to base64 URL
        bg_image_url = get_image_base64(img)
        
        col_ui, col_canvas = st.columns([1, 4])
        with col_ui:
            sel_cls = st.selectbox("Class", p['product_list'], key=f"cls_{img_id}")
            if st.button("Submit Annotation", use_container_width=True):
                st.session_state[f"save_{img_id}"] = True

        with col_canvas:
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                background_image=bg_image_url,  # USE THE URL HERE
                height=img.height,
                width=img.width,
                drawing_mode="rect",
                key=f"canvas_{img_id}",
            )

        if st.session_state.get(f"save_{img_id}"):
            if canvas_result.json_data:
                objects = canvas_result.json_data["objects"]
                yolo_anns = []
                for obj in objects:
                    if obj["type"] == "rect":
                        w_norm, h_norm = obj["width"] / img.width, obj["height"] / img.height
                        x_center = (obj["left"] / img.width) + (w_norm / 2)
                        y_center = (obj["top"] / img.height) + (h_norm / 2)
                        yolo_anns.append({'class': sel_cls, 'bbox': [x_center, y_center, w_norm, h_norm]})
                
                p['annotations'].setdefault(img_id, {})[st.session_state.username] = yolo_anns
                p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Completed"
                save_json(PROJECTS_FILE, projs)
                st.rerun()

        if projs:
            sel_p = st.selectbox("Select Project", list(projs.keys()))
            p = projs[sel_p]
            
            t1, t2, t3 = st.tabs(["Upload Images", "Assignments", "Export Data"])
            
            with t1:
                up = st.file_uploader("Upload Raw Images", accept_multiple_files=True, type=['jpg','jpeg','png'])
                if up and st.button("Save to Server"):
                    for f in up:
                        id = str(uuid.uuid4())
                        with open(os.path.join(IMAGES_DIR, f"{id}.png"), "wb") as img_f: img_f.write(f.getvalue())
                        p['images'].append({'id': id, 'date': datetime.now().strftime("%Y-%m-%d")})
                    save_json(PROJECTS_FILE, projs)
                    st.success("Uploaded successfully.")
            
            with t2:
                users_list = list(load_json(USERS_FILE).keys())
                target_u = st.selectbox("Assign to User", users_list)
                if st.button("Grant Access"):
                    if target_u not in p['access_users']: p['access_users'].append(target_u)
                    save_json(PROJECTS_FILE, projs)
                
                if p['access_users']:
                    u_to_assign = st.selectbox("Assign Images to", p['access_users'], key="assign_u")
                    done_imgs = p['assignments'].get(u_to_assign, [])
                    avail = [i['id'] for i in p['images'] if i['id'] not in done_imgs]
                    sel_imgs = st.multiselect("Select Images", avail)
                    if st.button("Confirm Assignment"):
                        p['assignments'].setdefault(u_to_assign, []).extend(sel_imgs)
                        save_json(PROJECTS_FILE, projs)
                        st.rerun()
            
            with t3:
                st.write("Generate YOLO training labels for all completed images.")
                if st.button("📦 Download YOLO Dataset"):
                    download_yolo(sel_p, p)

    elif menu == "Review Work":
        review_ui(projs)

    elif menu == "User Accounts":
        st.header("User Management")
        u_acc = load_json(USERS_FILE)
        with st.form("add_user"):
            new_un = st.text_input("New Username")
            new_pw = st.text_input("New Password")
            if st.form_submit_button("Create User"):
                u_acc[new_un] = {'password': new_pw}
                save_json(USERS_FILE, u_acc)
                st.success("User Created")

# --- USER PANEL ---
def user_page():
    st.sidebar.title(f"User: {st.session_state.username}")
    st.sidebar.button("Logout", on_click=logout)
    
    projs = load_json(PROJECTS_FILE)
    my_projs = [n for n, p in projs.items() if st.session_state.username in p['access_users']]
    
    if not my_projs:
        st.info("No projects assigned yet. Contact Admin.")
        return

    sel_p = st.selectbox("Select Project", my_projs)
    p = projs[sel_p]
    my_imgs = p['assignments'].get(st.session_state.username, [])
    
    # Filter only pending images
    pending = [i for i in my_imgs if p.get('statuses', {}).get(i, {}).get(st.session_state.username) != "Completed"]
    
    st.write(f"📊 Progress: {len(my_imgs) - len(pending)} / {len(my_imgs)} Completed")

    if not pending:
        st.balloons()
        st.success("All assigned images completed!")
        return

    # Work on the first pending image
    img_id = pending[0]
    img_path = os.path.join(IMAGES_DIR, f"{img_id}.png")
    
    if os.path.exists(img_path):
        img = Image.open(img_path)
        st.subheader("Draw Bounding Boxes")
        st.write("1. Select Class -> 2. Draw Rectangles -> 3. Click Submit")
        
        col_ui, col_canvas = st.columns([1, 4])
        
        with col_ui:
            sel_cls = st.selectbox("Product Class", p['product_list'], key=f"cls_{img_id}")
            if st.button("✅ Submit Annotation", use_container_width=True):
                st.session_state[f"trigger_save_{img_id}"] = True

        with col_canvas:
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                background_image=img,
                height=img.height,
                width=img.width,
                drawing_mode="rect",
                key=f"canvas_{img_id}",
            )

        if st.session_state.get(f"trigger_save_{img_id}"):
            if canvas_result.json_data:
                objects = canvas_result.json_data["objects"]
                yolo_anns = []
                for obj in objects:
                    if obj["type"] == "rect":
                        # YOLO format: class x_center y_center width height (normalized 0-1)
                        w_norm = obj["width"] / img.width
                        h_norm = obj["height"] / img.height
                        x_center = (obj["left"] / img.width) + (w_norm / 2)
                        y_center = (obj["top"] / img.height) + (h_norm / 2)
                        yolo_anns.append({'class': sel_cls, 'bbox': [x_center, y_center, w_norm, h_norm]})
                
                p['annotations'].setdefault(img_id, {})[st.session_state.username] = yolo_anns
                p.setdefault('statuses', {}).setdefault(img_id, {})[st.session_state.username] = "Completed"
                save_json(PROJECTS_FILE, projs)
                st.session_state[f"trigger_save_{img_id}"] = False
                st.rerun()

def review_ui(projs):
    st.header("Review Annotations")
    if not projs: return
    sel_p = st.selectbox("Project", list(projs.keys()))
    p = projs[sel_p]
    
    for u in p['access_users']:
        with st.expander(f"Work by {u}"):
            u_imgs = p['assignments'].get(u, [])
            for img_id in u_imgs:
                if img_id in p['annotations'] and u in p['annotations'][img_id]:
                    st.write(f"Image: {img_id}")
                    img = Image.open(os.path.join(IMAGES_DIR, f"{img_id}.png")).convert("RGB")
                    draw = ImageDraw.Draw(img)
                    for ann in p['annotations'][img_id][u]:
                        xc, yc, w, h = ann['bbox']
                        l, t = (xc - w/2) * img.width, (yc - h/2) * img.height
                        r, b = (xc + w/2) * img.width, (yc + h/2) * img.height
                        draw.rectangle([l, t, r, b], outline="red", width=3)
                    st.image(img, width=600)

def download_yolo(name, p):
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        # Create dataset structure
        for img_meta in p['images']:
            id = img_meta['id']
            img_p = os.path.join(IMAGES_DIR, f"{id}.png")
            if os.path.exists(img_p): z.write(img_p, f"images/{id}.png")
            
            label_content = ""
            if id in p['annotations']:
                for user, anns in p['annotations'][id].items():
                    # Only include if status is completed
                    if p.get('statuses', {}).get(id, {}).get(user) == "Completed":
                        for a in anns:
                            cls_idx = p['product_list'].index(a['class'])
                            coords = " ".join([f"{v:.6f}" for v in a['bbox']])
                            label_content += f"{cls_idx} {coords}\n"
            
            if label_content:
                z.writestr(f"labels/{id}.txt", label_content)
    
    st.download_button("💾 Download YOLO .zip", buf.getvalue(), f"{name}_yolo.zip", use_container_width=True)

if __name__ == "__main__":
    main()
