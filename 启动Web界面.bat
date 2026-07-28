"""
DIP3.0 Web界面启动脚本
"""
import subprocess
import sys

def main():
    print("=" * 60)
    print("DIP3.0本地目录测算系统 - Web界面启动")
    print("=" * 60)
    print()
    print("正在启动Web服务...")
    print("启动后请访问: http://localhost:8501")
    print()
    print("按 Ctrl+C 停止服务")
    print("-" * 60)
    
    # 启动streamlit
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        "F:/DIP/web/app.py",
        "--server.port", "8501",
        "--server.headless", "true"
    ]
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n服务已停止")

if __name__ == "__main__":
    main()
