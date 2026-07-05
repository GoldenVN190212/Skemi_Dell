import os
import subprocess
import ctypes
import sys

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def main():
    if not is_admin():
        print("Yêu cầu quyền Administrator để gỡ cài đặt Màn hình ảo...")
        # Re-run with admin rights
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        return

    print("=== Skemi Virtual Display Uninstaller ===")
    target_dir = os.path.join(os.getcwd(), "Skemi_Virtual_Display")

    if not os.path.exists(target_dir):
        print("Thư mục Skemi_Virtual_Display không tồn tại. Có vẻ như chưa được cài đặt.")
        return

    os.chdir(target_dir)
    print("Đang gỡ cài đặt Driver Màn Hình Ảo...")
    
    try:
        subprocess.run(["deviceinstaller64.exe", "stop", "usbmmidd"], check=False)
        print("\nGỠ CÀI ĐẶT THÀNH CÔNG!")
        print("Màn hình ảo đã được tắt và xóa khỏi hệ thống của bạn.")
    except Exception as e:
        print(f"\nCÓ LỖI XẢY RA: {e}")

if __name__ == "__main__":
    main()
