"""
Kịch bản PoC kiểm tra nhanh kết nối UCircle Auth (OTP/Session) và Quota Wavee.
Chạy: python poc_test_connection.py
"""
import sys
from pathlib import Path

# Nạp thư mục src vào sys.path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from tollcal.config import settings
from tollcal.ucircle.client import UCircleClient
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table


def main():
    rprint(Panel.fit("[bold cyan]KIỂM TRA KẾT NỐI TỚI UCIRCLE WAVEE[/bold cyan]"))
    rprint(f"• Supabase URL: [dim]{settings.supabase_url}[/dim]")
    rprint(f"• Email cấu hình: [bold]{settings.ucircle_email or 'Chưa nạp'}[/bold]")

    client = UCircleClient()
    try:
        rprint("\n[yellow]⏳ Đang kiểm tra phiên đăng nhập...[/yellow]")
        session = client.auth.login()
        rprint(f"[bold green]✔ Phiên làm việc hợp lệ![/bold green] User ID: [cyan]{session.user_id}[/cyan]")

        rprint("\n[yellow]⏳ Đang đọc hạn mức Wavee (RPC)...[/yellow]")
        caps = client.get_caps()

        table = Table(title="Hạn Mức Tài Khoản UCircle Wavee")
        table.add_column("Thuộc tính", style="cyan")
        table.add_column("Giá trị", style="green")

        table.add_row("Gói tài khoản", str(caps.tier))
        table.add_row("Thời lượng tối đa/video", f"{caps.max_seconds} giây")
        table.add_row("Dung lượng tối đa/video", f"{caps.max_mb} MB")
        if caps.quota_minutes_cap is not None:
            table.add_row("Tổng số phút lưu trữ", f"{caps.quota_minutes_cap} phút")
            table.add_row("Số phút đã dùng", f"{caps.quota_minutes_used} phút")
            table.add_row("Số phút còn lại", f"{caps.quota_minutes_remaining} phút")

        rprint(table)
        rprint("\n[bold green]🎉 Gate A ĐẠT: Tài khoản và kết nối UCircle hoạt động 100%![/bold green]")

    except Exception as e:
        rprint(f"\n[bold red]✖ Chưa có phiên đăng nhập hợp lệ hoặc lỗi:[/bold red] {e}")
        rprint("\n👉 Hãy chạy lệnh sau để đăng nhập bằng mã OTP gửi về Email:")
        rprint("[bold yellow]python main.py login[/bold yellow]\n")


if __name__ == "__main__":
    main()
