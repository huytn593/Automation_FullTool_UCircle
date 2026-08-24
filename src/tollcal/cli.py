import sys
from pathlib import Path
from typing import Optional
import typer
from rich import print as rprint
from rich.table import Table
from rich.panel import Panel

from tollcal.domain.states import RightsBasis
from tollcal.observability.logging import console, logger
from tollcal.storage.database import init_database
from tollcal.storage.repositories import ChannelRepository, JobRepository
from tollcal.sync.orchestrator import SyncOrchestrator
from tollcal.ucircle.client import UCircleClient
from tollcal.media.temp_files import temp_manager

app = typer.Typer(
    name="tollcal",
    help="Hệ thống tự động hóa đồng bộ video TikTok sang UCircle Wavee.",
    add_completion=False,
)


@app.command()
def ui(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host lắng nghe"),
    port: int = typer.Option(8000, "--port", "-p", help="Cổng Web UI"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Không tự động mở trình duyệt"),
):
    """Khởi chạy giao diện Web UI trực quan, dễ dùng trên trình duyệt."""
    import socket
    import webbrowser
    import uvicorn

    def is_port_in_use(h: str, p: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((h, p)) == 0

    chosen_port = port
    while is_port_in_use(host, chosen_port):
        chosen_port += 1

    url = f"http://{host}:{chosen_port}"
    rprint(Panel.fit(
        f"[bold green]🚀 GIAO DIỆN WEB TOLLCAL ĐANG KHỞI CHẠY TẠI:[/bold green]\n"
        f"[bold cyan]{url}[/bold cyan]\n\n"
        f"[dim]Nhấn Ctrl+C để dừng máy chủ.[/dim]"
    ))

    if not no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run("tollcal.ui.server:app", host=host, port=chosen_port, log_level="info")


@app.command()
def login(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email tài khoản UCircle"),
):
    """Đăng nhập UCircle bằng Email và mã OTP (Tự động lưu Session vĩnh viễn)."""
    init_database()
    rprint(Panel.fit("[bold cyan]ĐĂNG NHẬP UCIRCLE BẰNG EMAIL & OTP[/bold cyan]"))

    client = UCircleClient()
    target_email = email or typer.prompt("Nhập Email tài khoản UCircle của bạn")
    
    try:
        rprint(f"\n[yellow]⏳ Đang gửi mã xác thực OTP tới [bold]{target_email}[/bold]...[/yellow]")
        client.auth.send_otp(target_email)
        rprint("[green]✔ Mã OTP đã được gửi! Vui lòng kiểm tra hộp thư đến (hoặc thư rác) của bạn.[/green]")

        otp_token = typer.prompt("\n👉 Nhập mã OTP gồm 6 chữ số vừa nhận được")
        rprint("\n[yellow]⏳ Đang xác thực mã OTP...[/yellow]")
        session = client.auth.verify_otp(target_email, otp_token)

        rprint(f"[bold green]🎉 Đăng nhập thành công![/bold green] User ID: [cyan]{session.user_id}[/cyan]")
        rprint("[dim]Phiên đăng nhập đã được lưu. Hệ thống sẽ tự động duy trì kết nối mà không cần nhập lại OTP.[/dim]")

        # Hiển thị thông tin hạn mức Wavee ngay sau khi đăng nhập
        caps = client.get_caps()
        table = Table(title="Hạn Mức Tài Khoản UCircle Wavee")
        table.add_column("Thuộc tính", style="cyan")
        table.add_column("Giá trị", style="green")
        table.add_row("Gói tài khoản", caps.tier)
        table.add_row("Thời lượng tối đa/video", f"{caps.max_seconds} giây")
        table.add_row("Dung lượng tối đa/video", f"{caps.max_mb} MB")
        if caps.quota_minutes_cap is not None:
            table.add_row("Tổng số phút lưu trữ", f"{caps.quota_minutes_cap} phút")
            table.add_row("Số phút đã dùng", f"{caps.quota_minutes_used} phút")
            table.add_row("Số phút còn lại", f"{caps.quota_minutes_remaining} phút")
        console.print(table)

    except Exception as e:
        rprint(f"[bold red]✖ Đăng nhập thất bại:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def send_otp(email: str = typer.Argument(..., help="Email tài khoản UCircle")):
    """Gửi mã OTP về email."""
    init_database()
    client = UCircleClient()
    try:
        client.auth.send_otp(email)
        rprint(f"[green]✔ Đã gửi mã OTP tới {email}.[/green]")
    except Exception as e:
        rprint(f"[red]✖ Lỗi gửi OTP:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def verify_otp(
    email: str = typer.Argument(..., help="Email tài khoản UCircle"),
    token: str = typer.Argument(..., help="Mã OTP 6 chữ số"),
):
    """Xác thực mã OTP và lưu phiên đăng nhập."""
    init_database()
    client = UCircleClient()
    try:
        session = client.auth.verify_otp(email, token)
        rprint(f"[bold green]✔ Đăng nhập thành công![/bold green] User ID: {session.user_id}")
    except Exception as e:
        rprint(f"[red]✖ Xác thực OTP thất bại:[/red] {e}")
        raise typer.Exit(code=1)


@app.command()
def test_ucircle():
    """Kiểm tra kết nối và hạn mức Wavee của tài khoản UCircle."""
    init_database()
    rprint(Panel.fit("[bold cyan]KIỂM TRA KẾT NỐI UCIRCLE WAVEE[/bold cyan]"))

    client = UCircleClient()
    try:
        session = client.auth.login()
        rprint(f"[green]✔ Đăng nhập thành công![/green] User ID: [bold]{session.user_id}[/bold]")
        
        caps = client.get_caps()
        table = Table(title="Hạn Mức Tài Khoản UCircle Wavee")
        table.add_column("Thuộc tính", style="cyan")
        table.add_column("Giá trị", style="green")

        table.add_row("Gói tài khoản (Tier)", caps.tier)
        table.add_row("Thời lượng tối đa/video", f"{caps.max_seconds} giây")
        table.add_row("Dung lượng tối đa/video", f"{caps.max_mb} MB")
        if caps.quota_minutes_cap is not None:
            table.add_row("Tổng số phút lưu trữ", f"{caps.quota_minutes_cap} phút")
            table.add_row("Số phút đã sử dụng", f"{caps.quota_minutes_used} phút")
            table.add_row("Số phút còn lại", f"{caps.quota_minutes_remaining} phút")

        console.print(table)
    except Exception as e:
        rprint(f"[bold red]✖ Kiểm tra kết nối thất bại:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def sync_url(
    url: str = typer.Argument(..., help="Link video TikTok (vt.tiktok.com hoặc tiktok.com/@user/video/...)"),
    visibility: str = typer.Option("public", "--visibility", "-v", help="Chế độ hiển thị (public / connections)"),
    circle_id: Optional[str] = typer.Option(None, "--circle-id", "-c", help="Circle ID nếu muốn gắn video vào Circle"),
    rights: str = typer.Option("owner", "--rights", "-r", help="Quyền sử dụng: owner, licensed, creator_oauth"),
    caption: Optional[str] = typer.Option(None, "--caption", help="Caption tùy chỉnh thay thế tiêu đề TikTok gốc"),
):
    """Đồng bộ một video TikTok đơn lẻ sang UCircle Wavee."""
    init_database()
    rights_basis = RightsBasis(rights) if rights in [e.value for e in RightsBasis] else RightsBasis.OWNER
    orchestrator = SyncOrchestrator()

    try:
        job = orchestrator.sync_single_video(
            source_url_or_path=url,
            visibility=visibility,
            circle_id=circle_id,
            rights_basis=rights_basis,
            custom_caption=caption,
            poll_encode=True,
        )
        rprint(f"[bold green]✔ Đồng bộ thành công! Trạng thái cuối: {job.state.value}[/bold green]")
    except Exception as e:
        rprint(f"[bold red]✖ Đồng bộ thất bại:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def sync_file(
    file_path: str = typer.Argument(..., help="Đường dẫn file video cục bộ (.mp4) trên máy"),
    visibility: str = typer.Option("public", "--visibility", "-v", help="Chế độ hiển thị (public / connections)"),
    circle_id: Optional[str] = typer.Option(None, "--circle-id", "-c", help="Circle ID nếu có"),
    caption: Optional[str] = typer.Option(None, "--caption", help="Tiêu đề / Caption bài viết"),
):
    """Đồng bộ một file video có sẵn trên máy lên UCircle Wavee (dùng để test không cần TikTok)."""
    init_database()
    path = Path(file_path)
    if not path.exists():
        rprint(f"[red]✖ Không tìm thấy file: {file_path}[/red]")
        raise typer.Exit(code=1)

    orchestrator = SyncOrchestrator()
    try:
        job = orchestrator.sync_single_video(
            source_url_or_path=str(path.absolute()),
            visibility=visibility,
            circle_id=circle_id,
            custom_caption=caption or path.stem,
            poll_encode=True,
        )
        rprint(f"[bold green]✔ Tải lên file thành công! Video ID: {job.ucircle_video_id}[/bold green]")
    except Exception as e:
        rprint(f"[bold red]✖ Upload file thất bại:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def add_channel(
    url: str = typer.Argument(..., help="URL trang cá nhân TikTok của creator (vd: https://www.tiktok.com/@creator)"),
    creator_id: str = typer.Argument(..., help="ID định danh creator"),
    rights: str = typer.Option("owner", "--rights", "-r", help="Quyền sở hữu (owner / licensed)"),
):
    """Thêm một kênh Creator vào danh sách theo dõi tự động."""
    init_database()
    rights_basis = RightsBasis(rights) if rights in [e.value for e in RightsBasis] else RightsBasis.OWNER
    ch = ChannelRepository.add_channel(url, creator_id, rights_basis)
    rprint(f"[green]✔ Đã thêm kênh vào danh sách theo dõi:[/green] {ch.channel_url} ({ch.creator_id})")


@app.command()
def list_channels():
    """Hiển thị danh sách các kênh TikTok đang được theo dõi."""
    init_database()
    channels = ChannelRepository.list_active_channels()
    if not channels:
        rprint("[yellow]Chưa có kênh nào trong danh sách theo dõi.[/yellow]")
        return

    table = Table(title="Danh Sách Kênh Theo Dõi")
    table.add_column("ID", style="cyan")
    table.add_column("Creator ID", style="bold")
    table.add_column("URL Kênh", style="blue")
    table.add_column("Quyền", style="green")
    table.add_column("Lần quét cuối", style="dim")

    for ch in channels:
        table.add_row(
            str(ch.id),
            ch.creator_id,
            ch.channel_url,
            ch.rights_basis.value,
            str(ch.last_scanned_at or "Chưa quét"),
        )
    console.print(table)


@app.command()
def list_jobs(limit: int = typer.Option(20, "--limit", "-n", help="Số lượng bản ghi hiển thị")):
    """Xem lịch sử các video đã đồng bộ."""
    init_database()
    jobs = JobRepository.list_jobs(limit=limit)
    if not jobs:
        rprint("[yellow]Lịch sử đồng bộ trống.[/yellow]")
        return

    table = Table(title=f"Lịch Sử Đồng Bộ ({len(jobs)} video gần nhất)")
    table.add_column("ID", style="cyan")
    table.add_column("Nguồn", style="magenta")
    table.add_column("Video ID Nguồn", style="bold")
    table.add_column("UCircle Video ID", style="green")
    table.add_column("Trạng thái", style="yellow")
    table.add_column("Thời gian (s)", justify="right")
    table.add_column("Ngày tạo", style="dim")

    for j in jobs:
        table.add_row(
            str(j.id),
            j.source_provider,
            j.source_video_id,
            j.ucircle_video_id or "—",
            j.state.value,
            f"{j.duration_seconds:.1f}s" if j.duration_seconds else "—",
            str(j.created_at)[:19],
        )
    console.print(table)


@app.command()
def daemon():
    """Khởi động Daemon quét định kỳ các kênh TikTok đã lưu."""
    init_database()
    from tollcal.scheduler.service import ChannelSyncDaemon
    d = ChannelSyncDaemon()
    d.start_blocking()


@app.command()
def export_excel(output: str = typer.Option("lich_su_dong_bo.xlsx", "--output", "-o", help="Đường dẫn file Excel đích")):
    """Xuất lịch sử đồng bộ từ SQLite ra file Excel (.xlsx / .csv)."""
    init_database()
    from tollcal.storage.excel_export import export_jobs_to_excel
    path = export_jobs_to_excel(Path(output))
    rprint(f"[bold green]✔ Đã xuất lịch sử ra file Excel:[/bold green] [cyan]{path.resolve()}[/cyan]")


@app.command()
def scan_channel(
    channel: str = typer.Argument(..., help="Link kênh TikTok hoặc @username (ví dụ @vokhactuyen hoặc https://www.tiktok.com/@vokhactuyen)"),
    limit: int = typer.Option(100, "--limit", "-l", help="Số lượng video tối đa muốn quét"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Xuất danh sách link ra file .txt hoặc .xlsx"),
    method: str = typer.Option("auto", "--method", "-m", help="Phương thức quét: auto, api, ytdlp, browser"),
):
    """Quét toàn bộ video từ một trang/kênh TikTok (tương tự TikTokLinkExtractor)."""
    from tollcal.sources.tiktok_channel_scanner import channel_scanner

    rprint(Panel.fit(f"[bold cyan]QUÉT TOÀN BỘ VIDEO KÊNH TIKTOK[/bold cyan]\nKênh: [yellow]{channel}[/yellow] | Giới hạn: [yellow]{limit}[/yellow] video"))
    
    with console.status("[bold green]Đang quét danh sách video..."):
        videos = channel_scanner.scan(channel_input=channel, max_videos=limit, method=method)

    if not videos:
        rprint("[yellow]⚠ Không tìm thấy video nào từ kênh này hoặc kênh bị ẩn/chặn.[/yellow]")
        return

    table = Table(title=f"Danh Sách Video Quét Được ({len(videos)} video)")
    table.add_column("STT", style="cyan", width=5)
    table.add_column("Video ID", style="magenta")
    table.add_column("Tiêu đề / Caption", style="white", max_width=45)
    table.add_column("Thời lượng", style="green")
    table.add_column("URL TikTok", style="blue")

    for idx, v in enumerate(videos, 1):
        table.add_row(
            str(idx),
            v.get("video_id", ""),
            (v.get("title") or "—")[:40],
            f"{v.get('duration', 0):.0f}s" if v.get("duration") else "—",
            v.get("url", ""),
        )
    console.print(table)

@app.command()
def search(
    query: str = typer.Argument(..., help="Từ khóa hoặc chủ đề muốn tìm (ví dụ: 'review xe', 'tin tức', '#haihuoc')"),
    limit: int = typer.Option(60, "--limit", "-l", help="Số lượng video muốn tìm"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Xuất danh sách ra file .txt hoặc .xlsx"),
    method: str = typer.Option("auto", "--method", "-m", help="Phương thức tìm kiếm: auto, api, browser"),
):
    """Tìm kiếm video TikTok theo Từ Khóa / Chủ Đề (Không lo bị dính Captcha)."""
    from tollcal.sources.tiktok_channel_scanner import channel_scanner

    rprint(Panel.fit(f"[bold cyan]TÌM KIẾM VIDEO TIKTOK THEO TỪ KHÓA[/bold cyan]\nTừ khóa: [yellow]\"{query}\"[/yellow] | Số lượng: [yellow]{limit}[/yellow] video"))
    
    with console.status("[bold green]Đang tìm kiếm danh sách video..."):
        videos = channel_scanner.search(keywords=query, max_videos=limit, method=method)

    if not videos:
        rprint("[yellow]⚠ Không tìm thấy video nào phù hợp với từ khóa này.[/yellow]")
        return

    table = Table(title=f"Kết Quả Tìm Kiếm: \"{query}\" ({len(videos)} video)")
    table.add_column("STT", style="cyan", width=5)
    table.add_column("Kênh/User", style="magenta")
    table.add_column("Tiêu đề / Caption", style="white", max_width=45)
    table.add_column("Lượt xem", style="green")
    table.add_column("URL TikTok", style="blue")

    for idx, v in enumerate(videos, 1):
        views_str = f"{v.get('views', 0):,}" if v.get("views") else "—"
        table.add_row(
            str(idx),
            v.get("creator_id", "—"),
            (v.get("title") or "—")[:40],
            views_str,
            v.get("url", ""),
        )
    console.print(table)

    if output:
        out_path = Path(output)
        if out_path.suffix.lower() in (".xlsx", ".xls"):
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Videos"
            ws.append(["Link TikTok (Bắt buộc)", "Caption Tùy Chỉnh (Tùy chọn)", "Chế Độ Hiển Thị", "Circle ID"])
            for v in videos:
                ws.append([v["url"], v.get("title", ""), "public", ""])
            wb.save(out_path)
            rprint(f"[bold green]✔ Đã xuất {len(videos)} video ra file Excel:[/bold green] [cyan]{out_path.resolve()}[/cyan]")
        else:
            with open(out_path, "w", encoding="utf-8") as f:
                for v in videos:
                    f.write(v["url"] + "\n")
            rprint(f"[bold green]✔ Đã xuất {len(videos)} link ra file text:[/bold green] [cyan]{out_path.resolve()}[/cyan]")


if __name__ == "__main__":
    app()



