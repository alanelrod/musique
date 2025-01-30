import os
import time
import threading
import tkinter as tk
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import lyricsgenius
from google.cloud import translate
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up Google Cloud Translation API credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
translate_client = translate.Client()

# Set up Spotipy for Spotify API access
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope="user-read-playback-state",
    cache_path=".spotipy_cache"
))

# Set up Genius API client
genius = lyricsgenius.Genius(os.getenv("GENIUS_ACCESS_TOKEN"))


# Cache for translations
translation_cache = {}

def get_current_song():
    playback = sp.current_playback()
    if playback and playback['is_playing']:
        song = playback['item']['name']
        artist = playback['item']['artists'][0]['name']
        position = playback['progress_ms'] / 1000  # Current song position in seconds
        duration = playback['item']['duration_ms'] / 1000  # Song duration in seconds
        return song, artist, position, duration
    return None, None, None, None

def clean_text(text):
    """Remove unwanted artifacts, HTML entities, and common phrases while preserving formatting."""
    # Remove contributors line (e.g., "77 Contributors")
    text = re.sub(r"^\d+ Contributors.*\n", "", text)
    
    # Remove any tags or stage directions in square brackets (e.g., "[Chorus]", "[Verse 1]")
    text = re.sub(r"\[.*?\]", "", text)
    
    # Remove any "You might also like" suggestions, typically added by lyrics providers
    text = re.sub(r"You might also like.*\n", "", text, flags=re.IGNORECASE)
    
    # Remove any trailing "Embed" text with optional preceding digits (e.g., "198Embed" or just "Embed")
    text = re.sub(r"\d*Embed$", "", text, flags=re.IGNORECASE)

    text = re.sub(r"&#39;|&quot;|&amp;", "", text)
    

    return text.strip()


def fetch_lyrics(song_title, artist_name):
    try:
        song = genius.search_song(song_title, artist_name)
        if song:
            cleaned_lyrics = clean_text(song.lyrics)
            return cleaned_lyrics
        else:
            return "Lyrics not found"
    except Exception as e:
        print(f"Error fetching lyrics: {e}")
        return "Error fetching lyrics"

def translate_lyrics(lyrics, target_language="en"):
    if lyrics in translation_cache:
        return translation_cache[lyrics]
    
    try:
        # Split lyrics by lines and translate each line to preserve formatting
        lines = lyrics.splitlines()
        translated_lines = []
        for line in lines:
            if line.strip():  # Avoid translating empty lines
                translation = translate_client.translate(line, target_language=target_language)
                translated_lines.append(translation['translatedText'])
            else:
                translated_lines.append("")  # Preserve empty lines
        cleaned_translation = "\n".join(translated_lines)
        
        translation_cache[lyrics] = cleaned_translation
        return cleaned_translation
    except Exception as e:
        print(f"Error during translation: {e}")
        return "Translation failed"

def update_lyrics_display(root, original_text, translated_text, lyrics, translation):
    original_text.delete("1.0", tk.END)
    original_text.insert(tk.END, lyrics)
    translated_text.delete("1.0", tk.END)
    translated_text.insert(tk.END, translation)

def create_popup():
    root = tk.Tk()
    root.title("Lyrics Translation")

    original_text = tk.Text(root, height=20, width=50, wrap="word")
    original_text.pack(side=tk.LEFT, fill="both", expand=True)

    translated_text = tk.Text(root, height=20, width=50, wrap="word")
    translated_text.pack(side=tk.RIGHT, fill="both", expand=True)

    return root, original_text, translated_text

def song_monitor(root, original_text, translated_text):
    current_song = None
    displayed_lyrics = None
    last_update_time = 0

    while True:
        song, artist, position, duration = get_current_song()
        current_time = time.time()

        if song and artist:
            # If a new song or position is at the start, wait 5 seconds for continuous listening
            if (song, artist) != current_song or position < 5:
                # Update current_song after 5 seconds of continuous listening
                if current_time - last_update_time >= 5:
                    current_song = (song, artist)
                    print(f"Fetching lyrics for: {song} by {artist}")

                    # Fetch lyrics and translate only if the song has changed
                    lyrics = fetch_lyrics(song, artist)
                    if lyrics:
                        translation = translate_lyrics(lyrics)
                        # Schedule UI update on the main thread
                        root.after(0, update_lyrics_display, root, original_text, translated_text, lyrics, translation)
                        displayed_lyrics = lyrics
                    last_update_time = current_time
            elif position >= duration - 1:  # Reset when the song ends
                current_song = None
        else:
            # Clear display if nothing is playing
            if displayed_lyrics is not None:
                root.after(0, update_lyrics_display, root, original_text, translated_text, "No song is playing.", "")
                displayed_lyrics = None

        time.sleep(1)  # Check playback status every second

def main():
    root, original_text, translated_text = create_popup()

    # Start the song monitor in a separate thread
    threading.Thread(target=song_monitor, args=(root, original_text, translated_text), daemon=True).start()
    
    # Start the Tkinter main loop in the main thread
    root.mainloop()

main()
