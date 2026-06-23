import streamlit as st
import time
import cv2
from PIL import Image
import requests
import os

# Ρύθμιση Σελίδας
st.set_page_config(page_title="Whale Pipeline", page_icon="🐳", layout="centered")

# Αρχικοποίηση Session States
if "step" not in st.session_state:
    st.session_state.step = 1
if "local_video" not in st.session_state:
    st.session_state.local_video = None

# Συναρτήση για την εξαγωγή frame
def extract_frame(video_path, time_in_seconds):
    if not video_path or not os.path.exists(video_path):
        return None
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30  
            
        frame_id = int(fps * time_in_seconds)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(frame_rgb)
    except Exception as e:
        st.error(f"OpenCV Error: {e}")
    return None

# TopBar / Navigation
st.title("🐳 Whale Pipeline")

cols = st.columns(4)
steps_titles = ["1. Discovery", "2. Frames", "3. Review", "4. Final Video"]
for i, title in enumerate(steps_titles, 1):
    with cols[i-1]:
        if st.session_state.step == i:
            st.markdown(f"**🔵 {title}**")
        elif st.session_state.step > i:
            st.markdown(f"✅ {title}")
        else:
            st.markdown(f"⚪ {title}")

if st.session_state.step > 1:
    if st.button("⬅️ Back", key="back_btn"):
        st.session_state.step -= 1
        st.rerun()

st.markdown("---")

# ==========================================
# STEP 1: DISCOVERY
# ==========================================
if st.session_state.step == 1:
    st.subheader("Step 1 — Discovery")
    
    # Χρήση ενός απόλυτα έγκυρου open-source MP4 για τις δοκιμές σου
    reel_url = st.text_input(
        "Εισάγετε το Instagram Reel URL:", 
        value="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
        placeholder="https://instagram.com/reel/..."
    )
    
    if st.button("Download Video", type="primary"):
        with st.spinner("Downloading video via requests..."):
            try:
                local_filename = "input_video.mp4"
                
                # Προσθήκη Headers για να μην μας μπλοκάρει κανένα firewall
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                response = requests.get(reel_url, headers=headers, stream=True)
                
                if response.status_code == 200:
                    with open(local_filename, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=1024*1024):
                            if chunk:
                                f.write(chunk)
                    
                    # Έλεγχος αν το αρχείο υπάρχει και έχει μέγεθος
                    if os.path.exists(local_filename) and os.path.getsize(local_filename) > 0:
                        st.session_state.local_video = local_filename
                        st.success(f"Επιτυχές κατέβασμα! Μέγεθος αρχείου: {os.path.getsize(local_filename) / (1024*1024):.2f} MB")
                        time.sleep(1)
                        st.session_state.step = 2
                        st.rerun()
                    else:
                        st.error("Το αρχείο δημιουργήθηκε αλλά είναι άδειο (0 bytes).")
                else:
                    st.error(f"Ο server επέστρεψε σφάλμα: HTTP Status {response.status_code}")
                    
            except Exception as e:
                st.error(f"Σφάλμα κατά τη διάρκεια του download: {e}")

# ==========================================
# STEP 2: FRAME SELECTION
# ==========================================
elif st.session_state.step == 2:
    st.subheader("Step 2 — Frame Selection")
    
    st.write("### 📺 Video Player")
    if st.session_state.local_video and os.path.exists(st.session_state.local_video):
        # Δίνουμε απευθείας το string path στο st.video
        st.video(st.session_state.local_video)
    else:
        st.error("Το τοπικό αρχείο βίντεο δεν βρέθηκε στο σύστημα.")
    
    st.markdown("---")
    
    st.write("### 🤖 AI Recommended Thumbs")
    thumb_cols = st.columns(2)
    
    frame_hook = extract_frame(st.session_state.local_video, 1)
    frame_moment = extract_frame(st.session_state.local_video, 3)
    
    with thumb_cols[0]:
        if frame_hook:
            st.image(frame_hook, caption="Opening Hook @ 1s", use_container_width=True)
        else:
            st.error("Αδυναμία φόρτωσης Hook Frame")
            
    with thumb_cols[1]:
        if frame_moment:
            st.image(frame_moment, caption="Key Moment @ 3s", use_container_width=True)
        else:
            st.error("Αδυναμία φόρτωσης Moment Frame")

    st.markdown("---")

    st.write("### 🎞️ Filmstrip Scrubber")
    custom_time = st.slider("Σύρετε για να διαλέξετε custom δευτερόλεπτο:", min_value=0, max_value=10, value=2)
    
    st.write(f"📸 **Live Preview στο δευτερόλεπτο: {custom_time}s**")
    custom_frame = extract_frame(st.session_state.local_video, custom_time)
    
    if custom_frame:
        st.image(custom_frame, width=350, caption=f"Επιλεγμένο Frame ({custom_time}s)")
    else:
        st.warning("Μετακινήστε ελαφρώς τον slider ή βεβαιωθείτε ότι το βίντεο έχει διάρκεια.")

    st.markdown("---")
    if st.button("Generate Image", type="primary"):
        st.session_state.step = 3
        st.rerun()

# ==========================================
# STEPS 3 & 4 (Παραμένουν ως έχουν)
# ==========================================
elif st.session_state.step == 3:
    st.subheader("Step 3 — Review Image")
    st.info("Preview Mode")
    if st.button("✅ Εγκρίνω", type="primary"):
        st.session_state.step = 4
        st.rerun()

elif st.session_state.step == 4:
    st.subheader("Step 4 — Final Video")
    if st.session_state.local_video and os.path.exists(st.session_state.local_video):
        st.video(st.session_state.local_video)
    if st.button("🏁 Start New Pipeline", type="secondary"):
        if st.session_state.local_video and os.path.exists(st.session_state.local_video):
            os.remove(st.session_state.local_video)
        st.session_state.local_video = None
        st.session_state.step = 1
        st.rerun()
