import os  # 'os' kütüphanesini import et (Ortam Değişkenleri için)
from flask import Flask, render_template, request, redirect, session, url_for
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
from bs4 import BeautifulSoup

# Flask uygulamasını başlat
app = Flask(__name__)

# --- GÜVENLİK GÜNCELLEMESİ ---
# Artık gizli bilgileri koda yazmıyoruz, Render'dan alacağız.
app.secret_key = os.environ.get("SECRET_KEY")
CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("REDIRECT_URI")  # Bunu da Render'dan alacağız
# --------------------------------

SCOPE = "playlist-modify-private"

# Spotipy OAuth yöneticisi
sp_oauth = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE,
    cache_path=None  # <-- PythonAnywhere hatasından öğrendiğimiz düzeltme
)


@app.route('/')
def index():
    """Ana sayfa - Tarih formunu veya giriş sayfasını gösterir."""
    token_info = session.get('token_info', None)
    if not token_info:
        # Giriş yapmamışsa, login.html sayfasını göster
        return render_template('login.html')

    # Giriş yapmışsa, tarih formunu göster
    return render_template('index.html')


@app.route('/login')
def login():
    """Kullanıcıyı Spotify giriş sayfasına yönlendirir."""
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


@app.route('/callback')
def callback():
    """Spotify'dan gelen yönlendirmeyi yakalar."""
    # URL'den gelen 'code'u al ve token ile değiştir
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)

    # Token'ı kullanıcının oturumuna (session) kaydet
    session['token_info'] = token_info

    # Kullanıcıyı ana sayfaya (artık giriş yapmış olarak) yönlendir
    return redirect(url_for('index'))


@app.route('/create_playlist', methods=['POST'])
def create_playlist():
    """Formdan gelen tarih ile Billboard listesini çeker ve Spotify listesi oluşturur."""

    # 1. Oturumdan token'ı al
    token_info = session.get('token_info', None)
    if not token_info:
        return redirect(url_for('login'))

    if sp_oauth.is_token_expired(token_info):
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session['token_info'] = token_info

    # 2. Spotify objesini kullanıcıya ait token ile oluştur
    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_id = sp.current_user()["id"]

    # 3. Formdan tarihi al
    date = request.form['date']

    # 4. Billboard Kazıma (Scraping) İşlemi

    # --- RENDER GÜNCELLEMESİ ---
    # PythonAnywhere proxy kodunu buradan kaldırdık.
    # Render'da proxy'ye gerek yok.
    # --------------------------

    header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"}
    billboard_url = "https://www.billboard.com/charts/hot-100/" + date

    response = requests.get(url=billboard_url, headers=header)  # proxies=... kaldırıldı

    soup = BeautifulSoup(response.text, 'html.parser')
    song_names_spans = soup.select("li ul li h3")
    song_names = [song.getText().strip() for song in song_names_spans]

    # 5. Spotify Arama ve URI Toplama
    song_uris = []
    year = date.split("-")[0]
    songs_not_found = []

    for song in song_names:
        result = sp.search(q=f"track:{song} year:{year}", type="track", limit=1)
        try:
            uri = result["tracks"]["items"][0]["uri"]
            song_uris.append(uri)
        except IndexError:
            print(f"{song} Spotify'da bulunamadı. Atlandı.")
            songs_not_found.append(song)

    # 6. Playlist Oluşturma ve Şarkı Ekleme
    if song_uris:
        playlist = sp.user_playlist_create(user=user_id, name=f"{date} Billboard 100", public=False)
        sp.playlist_add_items(playlist_id=playlist["id"], items=song_uris)

        # 7. Başarı Sayfasına Yönlendir
        return render_template('success.html', playlist_url=playlist['external_urls']['spotify'], date=date)
    else:
        return "Hiç şarkı bulunamadı."

# --- RENDER GÜNCELLEMESİ ---
# app.run() satırını siliyoruz. Render 'gunicorn' kullanacak.
# Eğer yerelde test etmek istersen bu satırları geçici olarak açabilirsin.
# if __name__ == '__main__':
#    app.run(debug=True, port=5000)
# ---------------------------