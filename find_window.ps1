Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W {
  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")]
  public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll", CharSet=CharSet.Auto)]
  public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll")]
  public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")]
  public static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);
  [DllImport("user32.dll")]
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
}
"@

Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
  $pid_ = $_.Id
  [W]::EnumWindows([W+EnumWindowsProc]{
    param($h, $l)
    $procId = 0
    [W]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    if ($procId -eq $pid_) {
      $sb = New-Object System.Text.StringBuilder 256
      [W]::GetWindowText($h, $sb, 256) | Out-Null
      $visible = [W]::IsWindowVisible($h)
      Write-Host "PID=$pid_ HWND=$h Visible=$visible Title='$($sb.ToString())'"
    }
    return $true
  }, [IntPtr]::Zero) | Out-Null
}
