param([long]$WindowHandle, [string]$OutputPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class TikTokWindowCapture {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
}
'@
$handle = [IntPtr]$WindowHandle
$title = [System.Text.StringBuilder]::new(512)
[void][TikTokWindowCapture]::GetWindowText($handle, $title, $title.Capacity)
if ($title.ToString() -notmatch '^TikTok Studio.*Google Chrome$') { throw 'Target is not the TikTok Studio Chrome window.' }
$rect = [TikTokWindowCapture+Rect]::new()
if (-not [TikTokWindowCapture]::GetWindowRect($handle, [ref]$rect)) { throw 'Cannot read target bounds.' }
$bitmap = [System.Drawing.Bitmap]::new(($rect.Right - $rect.Left), ($rect.Bottom - $rect.Top))
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$hdc = $graphics.GetHdc()
try {
  if (-not [TikTokWindowCapture]::PrintWindow($handle, $hdc, 2)) { throw 'Chrome refused the window capture.' }
} finally { $graphics.ReleaseHdc($hdc); $graphics.Dispose() }
try { $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png) } finally { $bitmap.Dispose() }
Write-Output $OutputPath
