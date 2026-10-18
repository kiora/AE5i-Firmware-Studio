/* SPDX-License-Identifier: AGPL-3.0-or-later */
#ifndef UNICODE
#define UNICODE
#endif
#define _UNICODE
#include <windows.h>
#include <wchar.h>
#include <stdio.h>

/* Small GUI launcher. No admin rights, shell commands or firmware operations. */
int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR args, int show) {
    wchar_t folder[32768], script[32768], python[32768], ps[32768], command[32768];
    DWORD n=GetModuleFileNameW(NULL,folder,32768);
    if(!n || n>=32000) {
        MessageBoxW(NULL,L"The application path is too long. Move the complete folder to a shorter path.",L"AE5i Firmware Studio",MB_OK|MB_ICONERROR);
        return 1;
    }
    wchar_t *slash=wcsrchr(folder,L'\\');
    if(!slash) return 1;
    *slash=0;
    if(_snwprintf(script,32768,L"%ls\\app\\Studio.ps1",folder)<0) return 1;
    if(_snwprintf(python,32768,L"%ls\\runtime\\python.exe",folder)<0) return 1;
    if(GetFileAttributesW(script)==INVALID_FILE_ATTRIBUTES || GetFileAttributesW(python)==INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(NULL,L"Please extract the entire ZIP, including app and runtime folders, then launch again.",L"AE5i Firmware Studio",MB_OK|MB_ICONERROR);
        return 2;
    }
    if(!GetSystemDirectoryW(ps,30000)) return 3;
    wcscat(ps,L"\\WindowsPowerShell\\v1.0\\powershell.exe");
    int written=_snwprintf(command,32768,L"\"%ls\" -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%ls\"",ps,script);
    if(written<0 || written>=32767) return 4;
    STARTUPINFOW si={0};PROCESS_INFORMATION pi={0};si.cb=sizeof(si);
    si.dwFlags=STARTF_USESHOWWINDOW;si.wShowWindow=SW_HIDE;
    if(!CreateProcessW(ps,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,folder,&si,&pi)) {
        wchar_t message[256];_snwprintf(message,256,L"Cannot start Windows PowerShell. Error: %lu",GetLastError());
        MessageBoxW(NULL,message,L"AE5i Firmware Studio",MB_OK|MB_ICONERROR);return 5;
    }
    CloseHandle(pi.hThread);CloseHandle(pi.hProcess);return 0;
}
