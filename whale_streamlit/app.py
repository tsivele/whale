import streamlit as st
import requests
import os

# --- ΒΑΣΙΚΟ SETUP ---
st.set_page_config(page_title="Whale Pipeline", page_icon="🐳")
st.title("🐳 Whale Pipeline")
st.markdown("**1. Discovery** | 2. Frames | 3. Review | 4. Final Video")

# --- STEP 1: DISCOVERY (ΛΗΨΗ ΜΕΣΩ HIKERAPI) ---
st.header("Step 1 — Discovery")
reel_url = st.text_input("Εισάγετε το Instagram Reel URL:")

if st.button("Download Video"):
    with st.spinner("Προσπάθεια λήψης του Reel μέσω API... ⏳"):
        # Ρυθμίσεις του HikerAPI
        api_url = "https://api.hikerapi.com/v1/share/url"
        headers = {
            "accept": "application/json",
            "X-API-KEY": st.secrets["HIKER_API_KEY"]  # Κρύβουμε το κλειδί στα secrets
        }
        params = {"url": reel_url}
        
        try:
            # 1. Ζητάμε από το HikerAPI το link του βίντεο
            response = requests.get(api_url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                video_download_url = data.get("download_url")
                
                if video_download_url:
                    # 2. Κατεβάζουμε το πραγματικό .mp4 αρχείο
                    vid_response = requests.get(video_download_url)
                    
                    # 3. Το αποθηκεύουμε στον server του Streamlit
                    with open("temp_reel.mp4", "wb") as f:
                        f.write(vid_response.content)
                        
                    st.success("✅ Το βίντεο κατέβηκε με επιτυχία!")
                else:
                    st.error("Το API λειτούργησε, αλλά δεν βρήκε το βίντεο. Σιγουρέψου ότι το Reel είναι δημόσιο.")
            else:
                st.error(f"Σφάλμα API: HTTP Status {response.status_code}")
                
        except Exception as e:
            st.error(f"Προέκυψε σφάλμα στο σύστημα: {e}")

st.divider()

# --- STEP 2: FRAME SELECTION (ΜΕ ΠΡΟΣΤΑΣΙΑ) ---
st.header("Step 2 — Frame Selection")

video_path = "temp_reel.mp4"

# Ελέγχουμε αν το αρχείο υπάρχει ΚΑΙ αν έχει μέγεθος πάνω από 50KB (άρα δεν είναι άδειο)
if os.path.exists(video_path) and os.path.getsize(video_path) > 50000:
    
    st.subheader("📺 Video Player")
    st.video(video_path)
    
    st.subheader("🎞️ Filmstrip Scrubber")
    # Εδώ βάζεις το slider σου. Πλέον το βίντεο υπάρχει, άρα δεν θα βγάζει error.
    second_to_extract = st.slider("Σύρετε για να διαλέξετε custom δευτερόλεπτο:", 0, 60, 2)
    
    st.info(f"📸 Έτοιμο για εξαγωγή frame στο δευτερόλεπτο: {second_to_extract}s")
    
    # ΕΔΩ: Μπορείς να βάλεις τον κώδικα του OpenCV (cv2) που είχες για να κόβει το καρέ
    
else:
    # Αν το βίντεο δεν υπάρχει ή απέτυχε η λήψη, κρύβουμε τα errors και δείχνουμε αυτό:
    st.warning("⚠️ Κάντε λήψη ενός έγκυρου βίντεο στο Step 1 για να ξεκλειδωθεί η επεξεργασία των καρέ.")
