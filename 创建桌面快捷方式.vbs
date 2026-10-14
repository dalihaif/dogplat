' ============================================================
'  狗狗管理平台 · 在桌面创建快捷方式
' ============================================================
Option Explicit

Dim fso, ws, base, desk, lnkPath, lnk, icoPath

Set fso = CreateObject("Scripting.FileSystemObject")
Set ws  = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
desk = ws.SpecialFolders("Desktop")
lnkPath = desk & "\狗狗管理平台.lnk"
icoPath = base & "\static\icon.ico"

' 改名前留下的旧快捷方式，顺手删掉
If fso.FileExists(desk & "\训犬工作平台.lnk") Then
    fso.DeleteFile desk & "\训犬工作平台.lnk", True
End If

Set lnk = ws.CreateShortcut(lnkPath)
lnk.TargetPath = base & "\启动服务.bat"
lnk.WorkingDirectory = base
lnk.Description = "狗狗管理平台 · 启动并打开"
If fso.FileExists(icoPath) Then
    lnk.IconLocation = icoPath
End If
lnk.Save

If fso.FileExists(lnkPath) Then
    MsgBox "桌面快捷方式已创建。" & vbCrLf & vbCrLf & _
           "以后双击桌面上的「狗狗管理平台」就能启动并使用。", 64, "狗狗管理平台"
Else
    MsgBox "创建失败，请检查桌面权限。", 16, "狗狗管理平台"
End If
