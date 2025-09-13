import requests
import time
import os
from supabase import create_client, Client

# --- Supabase setup ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  
BUCKET_NAME = "VIDEOS"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Instagram setup ---
IG_USER_ID = os.getenv("IG_USER_ID")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# --- Twitter API via RapidAPI ---
TWITTER_HOST = "twitter-api45.p.rapidapi.com"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

def get_trending_video(query):
    url = f"https://{TWITTER_HOST}/search.php"
    querystring = {"query": query, "search_type": "Top"}
    headers = {
        "x-rapidapi-host": TWITTER_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY
    }
    try:
        response = requests.get(url, headers=headers, params=querystring)
        data = response.json()
        for tweet in data.get("timeline", []):
            media = tweet.get("media", {})
            videos = media.get("video", [])
            for video in videos:
                variants = video.get("variants", [])
                mp4s = [v for v in variants if v.get("content_type") == "video/mp4" and "url" in v]
                if mp4s:
                    best_video = sorted(mp4s, key=lambda x: x.get("bitrate", 0), reverse=True)[0]
                    return {
                        "title": f"*{tweet.get('screen_name', query)}*",
                        "description": tweet.get("text", "No description"),
                        "hashtags": f"#{query.replace(' ', '')} #Telugu #Politics #AP",
                        "url": best_video["url"]
                    }
    except Exception as e:
        print("Twitter fetch error:", e)
    return None

# --- Supabase upload ---
def upload_video_to_supabase(video_url, file_name):
    res = requests.get(video_url, stream=True)
    if res.status_code != 200:
        raise Exception("Failed to fetch video")

    supabase.storage.from_(BUCKET_NAME).upload(
        file_name, res.content, {"content-type": "video/mp4"}
    )
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{file_name}"
    print("✅ Uploaded to Supabase:", public_url)
    return public_url

# --- Instagram flow ---
def create_media_container(video_url, caption):
    url = f"https://graph.instagram.com/v23.0/{IG_USER_ID}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN,
    }
    res = requests.post(url, data=payload)
    res_json = res.json()
    print("Step 1 Response:", res_json)
    return res_json.get("id")

def check_status(container_id):
    url = f"https://graph.instagram.com/v23.0/{container_id}"
    params = {"fields": "status_code", "access_token": ACCESS_TOKEN}
    while True:
        res = requests.get(url, params=params)
        res_json = res.json()
        print("Checking status:", res_json)
        status = res_json.get("status_code")
        if status == "FINISHED":
            return True
        elif status == "ERROR":
            raise Exception("❌ Upload failed")
        time.sleep(20)

def publish_media(container_id):
    url = f"https://graph.instagram.com/v23.0/{IG_USER_ID}/media_publish"
    payload = {"creation_id": container_id, "access_token": ACCESS_TOKEN}
    res = requests.post(url, data=payload)
    print("Step 3 Response:", res.json())

def delete_from_supabase(file_name):
    supabase.storage.from_(BUCKET_NAME).remove([file_name])
    print(f"🗑️ Deleted from Supabase: {file_name}")

# --- Run everything ---
if __name__ == "__main__":
    query = "YS Jagan"
    video_data = get_trending_video(query)
    if video_data:
        file_name = "trending.mp4"
        uploaded_url = upload_video_to_supabase(video_data["url"], file_name)

        # Caption auto-built from Twitter description + hashtags
        caption = f"""{video_data['description']}\n\n{video_data['hashtags']}"""

        container_id = create_media_container(uploaded_url, caption)
        if container_id and check_status(container_id):
            publish_media(container_id)
            delete_from_supabase(file_name)
