import os
import zipfile
import urllib.request

URL = "https://github.com/tamnd/tiktok-cli/releases/download/v0.2.1/tt_0.2.1_windows_amd64.zip"

def download_tt():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    zip_dest = os.path.join(app_dir, "tt_temp.zip")
    tt_dest = os.path.join(app_dir, "tt.exe")

    print(f"Đang tải tt.exe từ GitHub...")
    print(f"URL: {URL}")
    
    req = urllib.request.Request(
        URL, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    with urllib.request.urlopen(req, timeout=60) as response, open(zip_dest, 'wb') as out_file:
        out_file.write(response.read())

    print("Đang giải nén tt.exe...")
    with zipfile.ZipFile(zip_dest, 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            if file_info.filename.endswith("tt.exe") or file_info.filename == "tt.exe":
                file_info.filename = "tt.exe"
                zip_ref.extract(file_info, app_dir)
                break
    
    if os.path.exists(zip_dest):
        os.remove(zip_dest)

    if os.path.exists(tt_dest):
        print("\n✅ THÀNH CÔNG! Đã tải xong file 'tt.exe' vào thư mục.")
    else:
        print("\n❌ LỖI: Không tìm thấy tt.exe sau khi giải nén.")

if __name__ == "__main__":
    download_tt()
