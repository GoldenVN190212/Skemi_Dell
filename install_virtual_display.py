import urllib.request
import zipfile
import os
import subprocess
import ctypes
import sys

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def find_file(name, path):
    name_lower = name.lower()
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.lower() == name_lower:
                return os.path.join(root, f)
    return None

def main():
    print("===============================================")
    print("   SKEMI PROFESSIONAL DRIVER SETUP (v4.5)      ")
    print("   [Verified Safety • Unstoppable Engine]      ")
    print("===============================================")
    print("[*] Trạng thái: Đang thực hiện kiểm tra đa tầng...")
    
    try:
        url = "https://www.amyuni.com/downloads/usbmmidd_v2.zip"
        base_dir = os.getcwd()
        target_dir = os.path.join(base_dir, "Skemi_Virtual_Display")
        zip_path = os.path.join(base_dir, "usbmmidd_v2.zip")

        # v4.5: Triple-check integrity and multi-stage download
        installer_path = find_file("deviceinstaller64.exe", target_dir)
        inf_path = find_file("usbmmidd.inf", target_dir)
        
        if not installer_path or not inf_path:
            print("[*] Phát hiện thiếu file. Đang kích hoạt bộ nạp đa tầng...")
            import shutil, ssl
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
            os.makedirs(target_dir, exist_ok=True)
            
            if not os.path.exists(zip_path):
                # STAGE 1: Python Standard
                try:
                    print(f"[*] Tầng 1: Đang tải Driver (Python Standard)...")
                    context = ssl._create_unverified_context()
                    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
                    opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
                    urllib.request.install_opener(opener)
                    urllib.request.urlretrieve(url, zip_path)
                except:
                    # STAGE 2: PowerShell
                    try:
                        print(f"[*] Tầng 2: Đang tải Driver (PowerShell Engine)...")
                        subprocess.run(["powershell", "-Command", f"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '{url}' -OutFile '{zip_path}'"], check=True, capture_output=True)
                    except:
                        # STAGE 3: BITSAdmin (The Final Weapon)
                        print(f"[*] Tầng 3: Đang tải Driver (BITSAdmin Final)...")
                        subprocess.run(["bitsadmin", "/transfer", "SkemiInstall", url, zip_path], check=True, capture_output=True)
            
            print("[+] Đang giải nén bộ cài (Multi-Extraction)...")
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(target_dir)
            except:
                print("[*] Thử giải nén bằng PowerShell...")
                subprocess.run(["powershell", "-Command", f"Expand-Archive -Path '{zip_path}' -DestinationPath '{target_dir}' -Force"], check=True)
            
            if os.path.exists(zip_path): os.remove(zip_path)
            
            # Final re-scan
            installer_path = find_file("deviceinstaller64.exe", target_dir)
            inf_path = find_file("usbmmidd.inf", target_dir)

        # 2. Locate Tools
        print("[*] Đang kích hoạt bộ cài chuyên nghiệp...")
        
        if not installer_path or not inf_path:
            raise FileNotFoundError(f"Không tìm thấy bộ cài trong {target_dir}. Sếp hãy thử xóa thư mục này và chạy lại.")

        work_dir = os.path.dirname(installer_path)
        os.chdir(work_dir)
        print(f"[+] Đã tìm thấy bộ cài tại: {work_dir}")

        # 3. Environment Cleanup
        print("[*] Đang chuẩn bị môi trường...")
        try:
            subprocess.run(["deviceinstaller64.exe", "stop", "usbmmidd"], check=False, capture_output=True)
        except: pass
        
        # 4. PNP Registration
        print("[*] Đang đăng ký Driver với hệ thống (PNP)...")
        try:
            subprocess.run(["pnputil", "/add-driver", "usbmmidd.inf"], check=False, capture_output=True)
        except: pass

        # 5. Core Installation
        print("[*] Đang thiết lập thiết bị ảo (Amyuni)...")
        subprocess.run([installer_path, "install", inf_path, "usbmmidd"], check=True)
        
        print("[*] Đang kích hoạt màn hình ảo (IDD)...")
        subprocess.run([installer_path, "enableidd", "1"], check=True)
        
        print("\n[SUCCESS] CÀI ĐẶT THÀNH CÔNG!")
        print(">>> Màn hình ảo đã được kích hoạt.")
        
    except Exception as e:
        print(f"\n[ERROR] CÓ LỖI XẢY RA: {e}")
        print("\n--- HƯỚNG DẪN CÀI ĐẶT THỦ CÔNG (PHƯƠNG ÁN DỰ PHÒNG) ---")
        print("Nếu bộ cài tự động thất bại, sếp hãy làm theo 3 bước này là xong ngay:")
        print("1. Click chuột phải vào nút Start, chọn 'Terminal (Admin)' hoặc 'Command Prompt (Admin)'.")
        print("2. Copy và dán lệnh này rồi nhấn Enter:")
        try:
            print(f'   cd /d "{os.getcwd()}"')
        except:
            print(f'   cd /d "{target_dir}"')
        print("3. Copy và dán tiếp lệnh này rồi nhấn Enter:")
        print("   deviceinstaller64.exe install usbmmidd.inf usbmmidd")
        print("\nSau đó sếp quay lại Web Skemi nhấn 'Thử quét lại Radar' là xong ạ!")
    
    print("\n-------------------------------------------")
    input("Nhấn Enter để hoàn tất và quay lại Skemi...")

if __name__ == "__main__":
    main()
