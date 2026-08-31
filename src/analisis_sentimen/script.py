import os
import re
import pandas as pd
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")

# Daftar kata kunci pencarian video terkait laptop ODM
SEARCH_QUERIES = [
    "nyantech odm",
    "okemudin vs GTID",
    "support odm lokal",
    "laptop odm lokal",
    "perdebatan laptop odm",
    "review advan workplus",
    "review axioo pongo",
    "review axioo hype",
    "axioo vs advan laptop",
    "advan ai gen review"
]

TOTAL_MAX_COMMENTS = 10000
MAX_COMMENTS_PER_VIDEO = 1000
OUTPUT_FILE = "src/analisis_sentimen/yt_comments.csv"

def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    text = re.sub(r'&[a-zA-Z]+;', '', text)
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'(.)\1{2,}', r'\1\1', text) # Mengatasi typo memanjang (cth: baguuus -> baguus)
    
    # 1. Normalisasi variasi negasi gaul ke baku
    negation_dict = {
        r'\b(ga|gak|ngga|nggak|g|ndak|tak)\b': 'tidak',
        r'\btakda\b': 'tidak ada',
        r'\bblm\b': 'belum',
        r'\bkrg\b': 'kurang',
        r'\bgaada\b': 'tidak ada',
        r'\bgakada\b': 'tidak ada',
        r'\bgkada\b': 'tidak ada',
    }
    for pattern, replacement in negation_dict.items():
        text = re.sub(pattern, replacement, text)

    # 2. Hapus kata pendek KECUALI kata bermakna penting (opsional: lebih aman hapus step 1-2 huruf ini)
    # text = re.sub(r'\b\w{1}\b', '', text) # Cukup hapus kata 1 huruf saja jika diperlukan
    
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_video_ids_by_queries(api_key: str, queries: list[str], max_results_per_query: int = 25) -> list[str]:
    youtube = build("youtube", "v3", developerKey=api_key)
    collected_ids = set()

    for q in queries:
        print(f"[INFO] Mencari video untuk kata kunci: '{q}'")
        try:
            request = youtube.search().list(
                q=q,
                part="id",
                type="video",
                maxResults=min(50, max_results_per_query)
            )
            response = request.execute()

            for item in response.get("items", []):
                vid_id = item.get("id", {}).get("videoId")
                if vid_id:
                    collected_ids.add(vid_id)

        except HttpError as e:
            print(f"[ERROR] Gagal mencari video untuk query '{q}': {e}")

    return list(collected_ids)

def scrape_comments(api_key: str, video_ids: list[str]) -> list[dict]:
    youtube = build("youtube", "v3", developerKey=api_key)
    all_comments = []

    for vid in video_ids:
        if len(all_comments) >= TOTAL_MAX_COMMENTS:
            print(f"[INFO] Target total {TOTAL_MAX_COMMENTS} komentar tercapai. Menghentikan scraping.")
            break

        print(f"[INFO] Memproses Video ID: {vid} (Terkumpul: {len(all_comments)}/{TOTAL_MAX_COMMENTS})")
        next_page_token = None
        count_per_vid = 0

        try:
            while count_per_vid < MAX_COMMENTS_PER_VIDEO and len(all_comments) < TOTAL_MAX_COMMENTS:
                remaining_total = TOTAL_MAX_COMMENTS - len(all_comments)
                remaining_vid = MAX_COMMENTS_PER_VIDEO - count_per_vid
                fetch_limit = min(100, remaining_vid, remaining_total)

                request = youtube.commentThreads().list(
                    part="snippet",
                    videoId=vid,
                    maxResults=fetch_limit,
                    pageToken=next_page_token,
                    textFormat="plainText",
                    order="relevance"
                )
                response = request.execute()

                for item in response.get("items", []):
                    top_snippet = item["snippet"]["topLevelComment"]["snippet"]

                    comment_record = {
                        "comment_id" : item.get("id"),
                        "author_name": top_snippet.get("authorDisplayName"),
                        "author_channel_id": top_snippet.get("authorChannelId", {}).get("value"),
                        "comment": clean_text(top_snippet.get("textDisplay", "")),
                        "like_count": top_snippet.get("likeCount", 0),
                        "total_reply_count": item["snippet"].get("totalReplyCount", 0),
                        "published_at": top_snippet.get("publishedAt"),
                        "updated_at": top_snippet.get("updatedAt"),
                    }
                    
                    all_comments.append(comment_record)
                    count_per_vid += 1

                    if len(all_comments) >= TOTAL_MAX_COMMENTS:
                        break

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break

        except HttpError as e:
            print(f"[ERROR] Gagal mengambil komentar untuk {vid}: {e}")

    return all_comments

if __name__ == "__main__":
    # Mengumpulkan video ID dari query pencarian secara otomatis
    video_ids = get_video_ids_by_queries(API_KEY, SEARCH_QUERIES, max_results_per_query=20)
    print(f"[INFO] Total video ditemukan: {len(video_ids)}")

    # Menjalankan proses scraping komentar dengan batas maksimal 10.000
    comments = scrape_comments(API_KEY, video_ids)
    if comments:
        df = pd.DataFrame(comments)
        df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
        print(f"[SUCCESS] Total {len(comments)} komentar berhasil disimpan ke {OUTPUT_FILE}")