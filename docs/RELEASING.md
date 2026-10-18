# 发布流程 · GitHub Releases

**Source / 源码：** GitHub 仓库 `main` 分支。  
**Binary / 发布包：** GitHub Releases → ZIP + SHA256。

1. 将本 `AE5i-Firmware-Studio-Source-v1.4.11.zip` **解压**后上传到一个独立的 GitHub 仓库（推荐 `AE5i-Firmware-Studio`）。不能把源码 ZIP 当作仓库里唯一的文件。
2. 核查 `app/`、`tests/`、`docs/`、`scripts/` 和 `.gitignore` 是否在仓库根目录。源码仓库不得包含 `runtime/`、`.exe`、`.dll`、日志和实际固件。
3. 在仓库主页点击 `Releases` → `Draft a new release`。Tag 填 `v1.4.11`，target 为 `main`；标题为 `AE5i Firmware Studio v1.4.11 (Windows x64)`。
4. 将提供的 `AE5i-Firmware-Studio-v1.4.11-Windows-x64.zip` 和同名 `.sha256` 上传到 Release assets。建议选择 **Set as a pre-release**，因为原变更记录没有声明 Windows GUI 实机验证成功。
5. 发布后，使用另一台干净的 Windows 10/11 x64 机器完整解压并测试 EXE 启动、日志位置和离线固件解析。成功后可取消 pre-release 标记。

**PowerShell 校验：**

```powershell
Get-FileHash .\AE5i-Firmware-Studio-v1.4.11-Windows-x64.zip -Algorithm SHA256
```

**下次发布：** 在完整打包目录里执行：

```powershell
python scripts/make_release.py --input C:\path\to\complete-distribution --output dist --version 1.4.12
```

此脚本只负责验证目录和打 ZIP，不会下载依赖或编译 EXE。
