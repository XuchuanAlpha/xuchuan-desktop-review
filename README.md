# 续川桌面程序 v35.4.1

这是冻结候选版的公开审阅快照。桌面程序用 Python、Tkinter 和 SQLite 实现。随包提供格式卡、两份合成示例、离线测试、发布说明及校验清单。

## 独立核对

在解压目录打开终端。Windows 下使用带 Tkinter 的 Python 3.14，运行：

```powershell
Get-FileHash .\xuchuan_desktop.pyw -Algorithm SHA256
py -3.14 -B -m unittest -v test_public_snapshot
```

把源码哈希与 `RELEASE_FILES.sha256` 及 `xuchuan_release_manifest.json` 对照。
测试会独立读取交付文件并检查哈希、格式卡与示例，以及完整单笔记的解析结果。
Linux 可用 `python3 -B -m unittest -v test_public_snapshot`，Python 需包含 Tkinter。
哈希用于对照文件内容。核对来源时，请同时确认仓库所有者与对应的提交。

## Windows 试运行

另解压一份到空目录，运行 `py -3.14 xuchuan_desktop.pyw`。程序会在运行目录创建本地 SQLite 文件。使用合成数据即可进行界面检查。若做 API 测试，先在运行副本中检查请求预览，再决定是否发送。公开快照的 Windows 实机与联网验收仍待单独核对。

公开快照包含格式卡和两份示例。内部开发规则及其参考文件注入流程请使用内部验收包核对。上传仓库时使用本 ZIP 内容。试运行目录可能含 SQLite、备份和本机数据。
