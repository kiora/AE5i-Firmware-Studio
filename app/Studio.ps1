# SPDX-License-Identifier: AGPL-3.0-or-later
# Diagnostics are written even when the invisible EXE launcher is used.
$script:LogDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) 'log'
try {
    [IO.Directory]::CreateDirectory($script:LogDirectory) | Out-Null
} catch {
    $script:LogDirectory=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'AE5iFirmwareStudio\log'
    [IO.Directory]::CreateDirectory($script:LogDirectory) | Out-Null
}
$script:StartupLog = Join-Path $script:LogDirectory 'startup.log'
try { [IO.File]::AppendAllText($script:StartupLog, "`r`n=== " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " AE5i Studio startup ===`r`n") } catch {}
trap {
    try { [IO.File]::AppendAllText($script:StartupLog, ($_.ToString() + "`r`n" + $_.ScriptStackTrace + "`r`n")) } catch {}

    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'AE5i Firmware Studio - startup error') | Out-Null
    } catch { }
    break
}
$ErrorActionPreference = 'Stop'
try { [IO.File]::AppendAllText($script:StartupLog, ('PowerShell: ' + $PSVersionTable.PSVersion.ToString() + "`r`n")) } catch {}

# Request DPI awareness before WinForms creates its first native window.
# Avoid bitmap scaling where Windows otherwise enlarges a DPI-unaware UI.
try {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class AE5iDpi {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SetProcessDPIAware();
}
'@ -ErrorAction Stop
    [AE5iDpi]::SetProcessDPIAware() | Out-Null
} catch {
    try { [IO.File]::AppendAllText($script:StartupLog, "DPI awareness fallback: $($_.Exception.Message)`r`n") } catch {}
}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$script:HomeDir = Split-Path -Parent $PSScriptRoot
$script:Python = Join-Path $script:HomeDir 'runtime\python.exe'
$script:Engine = Join-Path $PSScriptRoot 'firmware.py'
$script:Source = $null
$script:Info = $null
$script:Replacements = @{}
$script:Pending = $null
$script:TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('AE5iStudio-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($script:TempRoot) | Out-Null
$bg = [Drawing.Color]::FromArgb(220,222,217)
$surface = [Drawing.Color]::FromArgb(236,237,232)
$surfaceAlt = [Drawing.Color]::FromArgb(248,248,245)
$surfaceSoft = [Drawing.Color]::FromArgb(209,214,207)
$border = [Drawing.Color]::FromArgb(191,199,190)
$fg = [Drawing.Color]::FromArgb(39,48,45)
$muted = [Drawing.Color]::FromArgb(91,102,97)
$accent = [Drawing.Color]::FromArgb(104,122,110)
$accentSoft = [Drawing.Color]::FromArgb(67,85,76)
$accentTeal = [Drawing.Color]::FromArgb(65,100,88)
$warning = [Drawing.Color]::FromArgb(139,95,46)
$errorColor = [Drawing.Color]::FromArgb(155,69,66)

$form = New-Object Windows.Forms.Form
$script:IconPath = Join-Path $script:HomeDir 'assets\AE5iStudio.ico'
if (Test-Path -LiteralPath $script:IconPath) { try { $form.Icon = New-Object Drawing.Icon($script:IconPath) } catch { } }
$form.Text = 'AE5i Firmware Studio 1.4.11 | Firmware Engineering Workbench'
$form.Size = New-Object Drawing.Size(1480,940)
$form.MinimumSize = New-Object Drawing.Size(1180,760)
$form.StartPosition = 'CenterScreen'
$workingArea=[Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$form.Size=New-Object Drawing.Size([Math]::Min(1480,[Math]::Max(600,$workingArea.Width-40)),[Math]::Min(940,[Math]::Max(500,$workingArea.Height-40)))
$form.MinimumSize=New-Object Drawing.Size([Math]::Min(1180,$form.Width),[Math]::Min(760,$form.Height))
$form.BackColor = $bg
$form.ForeColor = $fg
$form.Font = New-Object Drawing.Font('Microsoft YaHei UI',10)
$form.AutoScaleMode = 'Dpi'
$form.ShowInTaskbar = $true
$form.WindowState = [System.Windows.Forms.FormWindowState]::Normal
$form.Opacity = 1.0
$form.Add_Shown({
    try {
        $form.WindowState = [System.Windows.Forms.FormWindowState]::Normal
        $form.ShowInTaskbar = $true
        $form.Activate() | Out-Null
        [IO.File]::AppendAllText($script:StartupLog, "UI Shown; Visible=$($form.Visible); Handle=$($form.Handle); Bounds=$($form.Bounds)`r`n")
    } catch { try { [IO.File]::AppendAllText($script:StartupLog, "Shown error: $($_.Exception.Message)`r`n") } catch {} }
})
$form.Add_Activated({
    if (-not $script:ActivationLogged) {
        $script:ActivationLogged=$true
        try { [IO.File]::AppendAllText($script:StartupLog, "UI Activated`r`n") } catch {}
    }
})

$frame = New-Object Windows.Forms.Panel
$frame.Dock = 'Fill'
$frame.AutoScroll=$true
$frame.AutoScrollMinSize=New-Object Drawing.Size(1140,700)
$frame.Padding = New-Object Windows.Forms.Padding(16)
$frame.BackColor = $bg
$form.Controls.Add($frame)

$layout = New-Object Windows.Forms.TableLayoutPanel
$layout.Dock = 'Fill'
$layout.MinimumSize=New-Object Drawing.Size(1120,680)
$layout.ColumnCount = 1
$layout.RowCount = 4
$layout.BackColor = $bg
$layout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',239))) | Out-Null
$layout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',54))) | Out-Null
$layout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100))) | Out-Null
$layout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',150))) | Out-Null
$frame.Controls.Add($layout)

$headerCard = New-Object Windows.Forms.Panel
$headerCard.Dock = 'Fill'
$headerCard.BackColor = $surface
$headerCard.Padding = New-Object Windows.Forms.Padding(18,12,18,8)
$headerCard.BorderStyle = 'None'
$layout.Controls.Add($headerCard,0,0)

$titleArea = New-Object Windows.Forms.TableLayoutPanel
$titleArea.Dock = 'Top'
$titleArea.Height = 90
$titleArea.BackColor = $surface
$titleArea.ColumnCount = 2
$titleArea.RowCount = 1
$titleArea.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',76))) | Out-Null
$titleArea.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',24))) | Out-Null
$headerCard.Controls.Add($titleArea)

$titleStack = New-Object Windows.Forms.TableLayoutPanel
$titleStack.Dock = 'Fill'
$titleStack.BackColor = $surface
$titleStack.RowCount = 2
$titleStack.ColumnCount = 1
$titleStack.Margin = New-Object Windows.Forms.Padding(0)
$titleStack.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',49))) | Out-Null
$titleStack.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100))) | Out-Null
$titleArea.Controls.Add($titleStack,0,0)

$heading = New-Object Windows.Forms.Label
$heading.Text = 'AE5i Firmware Studio'
$heading.Dock = 'Fill'
$heading.AutoSize = $false
$heading.AutoEllipsis = $true
$heading.TextAlign = [Drawing.ContentAlignment]::MiddleLeft
$heading.Margin = New-Object Windows.Forms.Padding(0)
$heading.Font = New-Object Drawing.Font('Microsoft YaHei UI',16,[Drawing.FontStyle]::Bold,[Drawing.GraphicsUnit]::Point)
$heading.ForeColor = $fg
$titleStack.Controls.Add($heading,0,0)

$subHeading = New-Object Windows.Forms.Label
$subHeading.Text = '固件工程工作台  /  INSPECT  ·  EXTRACT  ·  PATCH  ·  VERIFY  ·  REBUILD'
$subHeading.AutoSize = $false
$subHeading.Dock = 'Fill'
$subHeading.AutoEllipsis = $true
$subHeading.TextAlign = [Drawing.ContentAlignment]::MiddleLeft
$subHeading.Margin = New-Object Windows.Forms.Padding(0)
$subHeading.Font = New-Object Drawing.Font('Microsoft YaHei UI',10,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Point)
$subHeading.ForeColor = $muted
$titleStack.Controls.Add($subHeading,0,1)

$badgeFlow = New-Object Windows.Forms.FlowLayoutPanel
$badgeFlow.Dock = 'Right'
$badgeFlow.FlowDirection = 'LeftToRight'
$badgeFlow.WrapContents = $false
$badgeFlow.AutoSize = $true
$badgeFlow.BackColor = $surface
$badgeFlow.Padding = New-Object Windows.Forms.Padding(0,7,0,0)
$titleArea.Controls.Add($badgeFlow,1,0)

function New-Badge([string]$text, $backColor, $foreColor) {
    $b = New-Object Windows.Forms.Label
    $b.AutoSize = $true
    $b.Text = '  ' + $text + '  '
    $b.BackColor = $backColor
    $b.ForeColor = $foreColor
    $b.Margin = New-Object Windows.Forms.Padding(6,0,0,0)
    $b.Padding = New-Object Windows.Forms.Padding(10,5,10,5)
    $b.Font = New-Object Drawing.Font('Microsoft YaHei UI',9,[Drawing.FontStyle]::Bold)
    return $b
}
$badgeFlow.Controls.Add((New-Badge 'LOCAL / OFFLINE' $surfaceSoft $accentTeal))


$toolbar = New-Object Windows.Forms.FlowLayoutPanel
$toolbar.Dock = 'Bottom'
$toolbar.Height = 104
$toolbar.Padding = New-Object Windows.Forms.Padding(0,2,0,0)
$toolbar.BackColor = $surface
$toolbar.WrapContents = $true
$toolbar.AutoScroll = $false
$headerCard.Controls.Add($toolbar)

$script:Buttons = New-Object 'System.Collections.Generic.List[System.Windows.Forms.Button]'
function New-Button([string]$text, [scriptblock]$action, [int]$width=104) {
    $b = New-Object Windows.Forms.Button
    $b.Text = $text
    $b.Width = $width
    $b.Height = 40
    $b.FlatStyle = 'Flat'
    $b.BackColor = $surfaceAlt
    $b.ForeColor = $fg
    $b.FlatAppearance.BorderColor = $border
    $b.FlatAppearance.BorderSize = 1
    $b.Cursor = [Windows.Forms.Cursors]::Hand
    $b.Font = New-Object Drawing.Font('Microsoft YaHei UI',10,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Point)
    # Measure with Windows' actual text renderer; reserve a generous DPI-safe inset.
    $measured = [Windows.Forms.TextRenderer]::MeasureText($text,$b.Font,(New-Object Drawing.Size(1600,120)),([Windows.Forms.TextFormatFlags]::SingleLine -bor [Windows.Forms.TextFormatFlags]::NoPrefix))
    $b.Width = [Math]::Max($width,[Math]::Ceiling($measured.Width + 38))
    $b.AutoSize = $false
    $b.TextAlign = [Drawing.ContentAlignment]::MiddleCenter
    $b.Margin = New-Object Windows.Forms.Padding(0,1,7,7)
    $b.Add_MouseEnter({
        if ($this.Enabled) {
            $this.BackColor = if ($this.Tag -eq 'primary') { [Drawing.Color]::FromArgb(100,110,107) } else { [Drawing.Color]::FromArgb(219,217,211) }
        }
    })
    $b.Add_MouseLeave({
        if ($this.Enabled) {
            $this.BackColor = if ($this.Tag -eq 'primary') { $accentTeal } else { $surfaceAlt }
        }
    })
    $b.Add_Click($action)
    $toolbar.Controls.Add($b)
    $script:Buttons.Add($b)
    return $b
}

function Add-ToolSeparator {
    $sep = New-Object Windows.Forms.Panel
    $sep.Width = 1
    $sep.Height = 22
    $sep.BackColor = $border
    $sep.Margin = New-Object Windows.Forms.Padding(3,7,10,8)
    $toolbar.Controls.Add($sep)
}

$sourceCard = New-Object Windows.Forms.Panel
$sourceCard.Dock = 'Fill'
$sourceCard.BackColor = $surface
$sourceCard.Padding = New-Object Windows.Forms.Padding(16,4,16,4)
$sourceCard.BorderStyle = 'None'
$layout.Controls.Add($sourceCard,0,1)

$fileLabel = New-Object Windows.Forms.Label
$fileLabel.Dock = 'Fill'
$fileLabel.AutoSize = $false
$fileLabel.AutoEllipsis = $true
$fileLabel.TextAlign = [Drawing.ContentAlignment]::MiddleLeft
$fileLabel.Margin = New-Object Windows.Forms.Padding(0)
$fileLabel.Text = '●  尚未载入固件   |   支持 GEMINI_PACK.BIN / ZIP   |   本地离线处理   |   文件修改全部另存'
$fileLabel.ForeColor = $accentSoft
$fileLabel.Font = New-Object Drawing.Font('Microsoft YaHei UI',10,[Drawing.FontStyle]::Bold)
$sourceCard.Controls.Add($fileLabel)

$contentCard = New-Object Windows.Forms.Panel
$contentCard.Dock = 'Fill'
$contentCard.BackColor = $surface
$contentCard.Padding = New-Object Windows.Forms.Padding(14)
$contentCard.BorderStyle = 'None'
$layout.Controls.Add($contentCard,0,2)

$tabs = New-Object Windows.Forms.TabControl
$tabs.Dock = 'Fill'
$tabs.Font = New-Object Drawing.Font('Microsoft YaHei UI',10,[Drawing.FontStyle]::Regular,[Drawing.GraphicsUnit]::Point)
$tabs.Padding = New-Object Drawing.Point(18,8)
$tabs.BackColor = $surface
$tabs.Appearance = 'Normal'
$tabs.DrawMode = [System.Windows.Forms.TabDrawMode]::OwnerDrawFixed
$tabs.SizeMode = [System.Windows.Forms.TabSizeMode]::Fixed
$tabs.ItemSize = New-Object Drawing.Size(168,48)
$tabs.Add_DrawItem({
    param($sender,$e)
    if ($e.Index -lt 0 -or $e.Index -ge $sender.TabPages.Count) {return}
    $selected = ($e.Index -eq $sender.SelectedIndex)
    $rect = $sender.GetTabRect($e.Index)
    $g = $e.Graphics
    $bgTab = if ($selected) { $surfaceSoft } else { $surface }
    $fgTab = if ($selected) { $accentSoft } else { $muted }
    $brush = New-Object Drawing.SolidBrush($bgTab)
    try { $g.FillRectangle($brush,$rect) } finally { $brush.Dispose() }
    if ($selected) {
        $lineBrush = New-Object Drawing.SolidBrush($accent)
        try { $g.FillRectangle($lineBrush,$rect.X,$rect.Bottom-3,$rect.Width,3) } finally { $lineBrush.Dispose() }
    }
    [Windows.Forms.TextRenderer]::DrawText($g,$sender.TabPages[$e.Index].Text,$sender.Font,$rect,$fgTab,([Windows.Forms.TextFormatFlags]::HorizontalCenter -bor [Windows.Forms.TextFormatFlags]::VerticalCenter -bor [Windows.Forms.TextFormatFlags]::EndEllipsis -bor [Windows.Forms.TextFormatFlags]::NoPadding -bor [Windows.Forms.TextFormatFlags]::NoPrefix))
})
$contentCard.Controls.Add($tabs)

function New-Tab([string]$name) {
    $t = New-Object Windows.Forms.TabPage
    $t.Text = $name
    $t.BackColor = $surface
    $t.ForeColor = $fg
    $t.Padding = New-Object Windows.Forms.Padding(14)
    $tabs.TabPages.Add($t)
    return $t
}
function New-TextBox {
    $t = New-Object Windows.Forms.TextBox
    $t.Multiline = $true
    $t.ReadOnly = $true
    $t.ScrollBars = 'Both'
    $t.WordWrap = $false
    $t.Dock = 'Fill'
    $t.BackColor = $surfaceAlt
    $t.ForeColor = $fg
    $t.BorderStyle = 'None'
    $t.Margin = New-Object Windows.Forms.Padding(6)
    $t.Font = $tabs.Font
    return $t
}

$overviewTab = New-Tab '固件信息'
$overviewLayout = New-Object Windows.Forms.TableLayoutPanel
$overviewLayout.Dock = 'Fill'
$overviewLayout.ColumnCount = 2
$overviewLayout.RowCount = 1
$overviewLayout.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',43))) | Out-Null
$overviewLayout.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent',57))) | Out-Null
$overviewTab.Controls.Add($overviewLayout)
$overviewFacts = New-Object Windows.Forms.ListView
$overviewFacts.Dock = 'Fill'
$overviewFacts.View = 'Details'
$overviewFacts.FullRowSelect = $true
$overviewFacts.HideSelection = $false
$overviewFacts.HeaderStyle = 'Nonclickable'
$overviewFacts.BackColor = $surfaceAlt
$overviewFacts.ForeColor = $fg
$overviewFacts.BorderStyle = 'None'
$overviewFacts.Font = New-Object Drawing.Font('Microsoft YaHei UI',10)
$overviewFacts.Columns.Add('项目',148) | Out-Null
$overviewFacts.Columns.Add('值',355) | Out-Null
$overviewLayout.Controls.Add($overviewFacts,0,0)
$overviewFacts.Add_Resize({ if ($overviewFacts.ClientSize.Width -gt 170) { $overviewFacts.Columns[1].Width = [Math]::Max(100,$overviewFacts.ClientSize.Width - 152) } })
$overview = New-TextBox
$overview.WordWrap = $true
$overview.ScrollBars = [Windows.Forms.ScrollBars]::Vertical
$overview.Margin = New-Object Windows.Forms.Padding(12,3,3,3)
$overviewLayout.Controls.Add($overview,1,0)
function Set-OverviewFact([string]$name, [string]$value) {
    $it = New-Object Windows.Forms.ListViewItem($name)
    $it.SubItems.Add($value) | Out-Null
    $overviewFacts.Items.Add($it) | Out-Null
}
Set-OverviewFact '状态' '等待载入固件'
Set-OverviewFact '执行方式' 'LOCAL / OFFLINE'
Set-OverviewFact '导入策略' '固定槽位，另存修改'

$overview.Text = "支持：已核验的 AE5i / SW.1.01.15 GEMINI 容器。`r`n`r`n载入后展示整包大小、MD5、SHA-256、版本、外层结构、分区信息和各层校验。`r`n`r`n导入采用固定槽位：较小载荷补零，超出原载荷槽位拒绝导入；闪存容量会单独显示。`r`n`r`n权限核对以当前载入文件为基准；建议从对应官方原包开始编辑。`r`n`r`nuboot2 厂商封装的内部算法尚未验证，因此仅允许原样回填。"

$partTab = New-Tab '分区表'
$grid = New-Object Windows.Forms.DataGridView
$grid.Dock='Fill';$grid.ReadOnly=$true;$grid.AllowUserToAddRows=$false;$grid.AllowUserToDeleteRows=$false
$grid.AutoGenerateColumns=$false;$grid.SelectionMode='FullRowSelect';$grid.MultiSelect=$false
$grid.AllowUserToResizeRows=$false;$grid.AutoSizeColumnsMode='None';$grid.ClipboardCopyMode='EnableAlwaysIncludeHeaderText'
$grid.BackgroundColor=$surfaceAlt;$grid.BorderStyle='None';$grid.RowHeadersVisible=$false
$grid.EnableHeadersVisualStyles=$false
$grid.ColumnHeadersDefaultCellStyle.BackColor=$surfaceSoft
$grid.ColumnHeadersDefaultCellStyle.Alignment='MiddleLeft'
$grid.ColumnHeadersDefaultCellStyle.ForeColor=$fg
$grid.DefaultCellStyle.BackColor=$surfaceAlt
$grid.DefaultCellStyle.ForeColor=$fg
$grid.DefaultCellStyle.SelectionBackColor=[Drawing.Color]::FromArgb(204,223,211)
$grid.DefaultCellStyle.SelectionForeColor=$fg
$grid.RowTemplate.Height=39
$grid.ColumnHeadersHeight=48
$grid.ColumnHeadersDefaultCellStyle.WrapMode = [System.Windows.Forms.DataGridViewTriState]::False
$grid.ColumnHeadersDefaultCellStyle.Padding = New-Object Windows.Forms.Padding(4,0,2,0)
$grid.ColumnHeadersHeightSizeMode='DisableResizing'
$grid.DefaultCellStyle.Font=New-Object Drawing.Font('Microsoft YaHei UI',10)
$grid.AlternatingRowsDefaultCellStyle.BackColor=[Drawing.Color]::FromArgb(242,244,239)
$grid.CellBorderStyle='SingleHorizontal'
$grid.GridColor=$border
$grid.DefaultCellStyle.Padding=New-Object Windows.Forms.Padding(5,0,5,0)
$grid.ColumnHeadersDefaultCellStyle.Font=New-Object Drawing.Font('Microsoft YaHei UI',10,[Drawing.FontStyle]::Bold)
@(@('name','分区',120),@('offset','包内偏移',128),@('relative','内层偏移',128),@('length','载荷长度 (B)',152),@('flash','闪存偏移',126),@('capacity','闪存容量 (B)',154),@('kind','格式',90),@('hash','分区 MD5',300),@('stage','暂存导入',112)) | ForEach-Object {
    $c=New-Object Windows.Forms.DataGridViewTextBoxColumn
    $c.Name=$_[0];$c.HeaderText=$_[1];$c.Width=$_[2]
    $c.SortMode='NotSortable'
    $c.HeaderCell.Style.WrapMode=[System.Windows.Forms.DataGridViewTriState]::False
    $grid.Columns.Add($c) | Out-Null
}
$grid.Columns['hash'].AutoSizeMode = [System.Windows.Forms.DataGridViewAutoSizeColumnMode]::Fill
$grid.Columns['hash'].MinimumWidth = 280
$grid.Columns['hash'].FillWeight = 100
$grid.AutoSizeRowsMode = [System.Windows.Forms.DataGridViewAutoSizeRowsMode]::None
$grid.DefaultCellStyle.WrapMode = [System.Windows.Forms.DataGridViewTriState]::False
$partTab.Controls.Add($grid)
$grid.Cursor=[Windows.Forms.Cursors]::Default
$grid.Add_MouseEnter({if (-not $script:Pending) {$grid.UseWaitCursor=$false;$grid.Cursor=[Windows.Forms.Cursors]::Default}})
$partitionMenu = New-Object Windows.Forms.ContextMenuStrip
$partitionMenu.Font = New-Object Drawing.Font('Microsoft YaHei UI',10)
$partitionMenu.BackColor = $surface
$partitionMenu.ForeColor = $fg
$menuExport = $partitionMenu.Items.Add('导出选中分区…')
$menuImport = $partitionMenu.Items.Add('导入分区镜像…')
$menuRebuild = $partitionMenu.Items.Add('转到 SquashFS 工具…')
$menuUndo = $partitionMenu.Items.Add('撤销该分区暂存')
$null = $partitionMenu.Items.Add((New-Object Windows.Forms.ToolStripSeparator))
$menuPermissions = $partitionMenu.Items.Add('查看 Linux 权限清单')
$menuCopyName = $partitionMenu.Items.Add('复制分区名称')
$menuCopyRow = $partitionMenu.Items.Add('复制整行信息')
$grid.ContextMenuStrip = $partitionMenu
$grid.Add_MouseDown({param($sender,$e)
    if ($e.Button -eq [Windows.Forms.MouseButtons]::Right) {
        $hit=$grid.HitTest($e.X,$e.Y)
        if ($hit.RowIndex -ge 0) {
            $grid.ClearSelection()
            $grid.Rows[$hit.RowIndex].Selected=$true
            if ($hit.ColumnIndex -ge 0) { $grid.CurrentCell=$grid.Rows[$hit.RowIndex].Cells[$hit.ColumnIndex] }
        }
    }
})
$partitionMenu.Add_Opening({param($sender,$e)
    $hasRow = ($grid.SelectedRows.Count -gt 0)
    foreach ($m in @($menuExport,$menuImport,$menuRebuild,$menuUndo,$menuPermissions,$menuCopyName,$menuCopyRow)) {$m.Enabled=$hasRow -and (-not $script:Pending)}
    if ($hasRow) {
        $partitionName=[string]$grid.SelectedRows[0].Cells['name'].Value
        $isSquash=$false
        if ($script:Info) { $isSquash = [string]$grid.SelectedRows[0].Cells['kind'].Value -eq 'SquashFS' }
        $menuRebuild.Enabled=$isSquash -and (-not $script:Pending)
        $menuUndo.Enabled=$script:Replacements.ContainsKey($partitionName) -and (-not $script:Pending)
    }
})
$menuCopyName.Add_Click({if($grid.SelectedRows.Count -gt 0){[Windows.Forms.Clipboard]::SetText([string]$grid.SelectedRows[0].Cells['name'].Value)}})
$menuCopyRow.Add_Click({if($grid.SelectedRows.Count -gt 0){$values=@(foreach($cell in $grid.SelectedRows[0].Cells){[string]$cell.Value});[Windows.Forms.Clipboard]::SetText(($values -join "`t"))}})
$menuExport.Add_Click({$exportSelectedButton.PerformClick()})
$menuImport.Add_Click({$importSelectedButton.PerformClick()})
$menuUndo.Add_Click({$undoSelectedButton.PerformClick()})
$menuPermissions.Add_Click({$permissionsButton.PerformClick()})
$menuRebuild.Add_Click({if ($grid.SelectedRows.Count -gt 0) { $partName=[string]$grid.SelectedRows[0].Cells['name'].Value; $squashPartition.SelectedItem=$partName; $tabs.SelectedTab=$squashTab }})


# Standalone SquashFS workspace, no dependency on partition table row selection.
$squashTab = New-Tab 'SquashFS 工具'
$squashWorkspace = New-Object Windows.Forms.TableLayoutPanel
$squashWorkspace.Dock='Fill';$squashWorkspace.ColumnCount=1;$squashWorkspace.RowCount=4
$squashWorkspace.Padding=New-Object Windows.Forms.Padding(20,18,20,12)
$squashWorkspace.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',52))) | Out-Null
$squashWorkspace.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',68))) | Out-Null
$squashWorkspace.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',64))) | Out-Null
$squashWorkspace.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100))) | Out-Null
$squashTab.Controls.Add($squashWorkspace)
$squashHeading=New-Object Windows.Forms.Label
$squashHeading.Text='SquashFS 文件系统工具';$squashHeading.Dock='Fill';$squashHeading.Font=New-Object Drawing.Font('Microsoft YaHei UI',14,[Drawing.FontStyle]::Bold)
$squashHeading.ForeColor=$fg
$squashWorkspace.Controls.Add($squashHeading,0,0)
$squashSelectorPanel=New-Object Windows.Forms.FlowLayoutPanel
$squashSelectorPanel.Dock='Fill';$squashSelectorPanel.WrapContents=$false
$squashSelectorPanel.BackColor=$surface
$squashWorkspace.Controls.Add($squashSelectorPanel,0,1)
$squashSelectLabel=New-Object Windows.Forms.Label
$squashSelectLabel.Text='选择文件系统分区';$squashSelectLabel.AutoSize=$true
$squashSelectLabel.Font=New-Object Drawing.Font('Microsoft YaHei UI',10)
$squashSelectLabel.Margin=New-Object Windows.Forms.Padding(2,10,14,0)
$squashSelectorPanel.Controls.Add($squashSelectLabel)
$squashPartition=New-Object Windows.Forms.ComboBox
$squashPartition.DropDownStyle=[Windows.Forms.ComboBoxStyle]::DropDownList
$squashPartition.Width=300;$squashPartition.Height=36
$squashPartition.Font=New-Object Drawing.Font('Microsoft YaHei UI',10)
$squashPartition.Margin=New-Object Windows.Forms.Padding(0,5,0,0)
$squashSelectorPanel.Controls.Add($squashPartition)
$squashActions=New-Object Windows.Forms.FlowLayoutPanel
$squashActions.Dock='Fill';$squashActions.BackColor=$surface;$squashActions.WrapContents=$false
$squashWorkspace.Controls.Add($squashActions,0,2)
$squashDescription=New-Object Windows.Forms.Label
$squashDescription.Dock='Fill';$squashDescription.AutoSize=$false
$squashDescription.Font=New-Object Drawing.Font('Microsoft YaHei UI',10)
$squashDescription.ForeColor=$muted
$squashDescription.Text="工作流程：选择 SquashFS 分区 → 解包到 Windows 目录并保存 Linux 元数据 → 编辑文件 → 从目录重建并验证。`r`n重建需要保留元数据清单；超过分区槽位或权限校验失败时不会暂存。"
$squashWorkspace.Controls.Add($squashDescription,0,3)
function Selected-SquashName {
    if (-not $script:Source) { throw '请先载入固件。' }
    if ($squashPartition.SelectedItem -eq $null) { throw '请先在 SquashFS 工具页选择一个分区。' }
    return [string]$squashPartition.SelectedItem
}
function Update-SquashPartitions {
    $previous=[string]$squashPartition.SelectedItem
    $squashPartition.Items.Clear()
    foreach ($part in $script:Info.partitions) {
        if ([string]$part.kind -eq 'SquashFS') { [void]$squashPartition.Items.Add([string]$part.name) }
    }
    if ($squashPartition.Items.Contains($previous)) { $squashPartition.SelectedItem=$previous }
    elseif ($squashPartition.Items.Count -gt 0) { $squashPartition.SelectedIndex=0 }
}

$checksTab=New-Tab '校验结果'
$checks=New-Object Windows.Forms.ListView
$checks.Dock='Fill';$checks.View='Details';$checks.FullRowSelect=$true;$checks.GridLines=$false
$checks.BackColor=$surfaceAlt;$checks.ForeColor=$fg;$checks.BorderStyle='None'
$checks.Font = New-Object Drawing.Font('Microsoft YaHei UI',10)
@(@('状态',85),@('校验项',430),@('详情',660)) | ForEach-Object {$checks.Columns.Add($_[0],$_[1]) | Out-Null}
$checksTab.Controls.Add($checks)

$permissionsTab=New-Tab '权限 / 文件清单';$permissions=New-TextBox;$permissions.WordWrap=$true;$permissions.ScrollBars=[Windows.Forms.ScrollBars]::Vertical;$permissionsTab.Controls.Add($permissions)
$permissions.Text='在分区表中选中 SquashFS 分区，再点“权限清单”。清单读取 Linux 元数据，不使用 Windows 文件属性。'
$helpTab=New-Tab '操作说明'
$help = New-Object Windows.Forms.RichTextBox
$help.Dock = 'Fill'
$help.ReadOnly = $true
$help.WordWrap = $true
$help.ScrollBars = [Windows.Forms.RichTextBoxScrollBars]::Vertical
$help.BorderStyle = 'None'
$help.BackColor = $surfaceAlt
$help.ForeColor = $fg
$help.Font = New-Object Drawing.Font('Microsoft YaHei UI',10)
$help.Margin = New-Object Windows.Forms.Padding(14)
$help.DetectUrls = $false
$helpTab.Controls.Add($help)
$help.Text=@"
1. 载入 BIN / ZIP：自动读取并检查固件。黄色 WARN 不等于通过厂商内部校验。
2. 分区表：选中一行后可导出、导入或查看 SquashFS 权限清单。
3. 全部分割：选择空目录，导出 19 项载荷、外层头、升级脚本、CSV、JSON 和权限清单。
4. 导入分区：修改先暂存；源固件保持原样。导入失败不会替换已暂存的文件。
5. 导入工程：选择此前分割目录；工程与当前源固件 SHA-256 必须一致。
6. 打包 BIN / ZIP：自动修正已支持的校验，再校验、比较权限并回读输出；附 .report.json。
7. 深度校验：额外解压读取全部 SquashFS 普通文件并计算 SHA-256，耗时更长。

支持范围
• 已核验 SW.1.01.15 容器；v10、v11、v12 同结构可读取。
• 自动维护外层/分区/脚本分块 MD5、标准 uImage CRC、S-record 行校验。
• 保留固定布局、长度、脚本命令与升级流程。不能将包内载荷长度当作闪存容量。
• 较小导入按原槽位补零；超长载荷拒绝，不扩容、不重排。
• 文件路径、类型、权限、UID/GID、软链接、硬链接关系需与当前源一致。
• 内置 squashfs-tools-ng 1.1.0：Windows 目录按原 Linux 元数据清单打包为 SquashFS，重建后严格核验。
• uboot2 image type=0x5A 是厂商封装；标准 CRC 不适用，仅允许原样回填。
• 校验通过代表已支持的结构与摘要一致，不代表签名认证或实车兼容认证。
• 工具不会连接、升级或刷写车辆。
"@

$bottomCard = New-Object Windows.Forms.Panel
$bottomCard.Dock = 'Fill'
$bottomCard.BackColor = $surface
$bottomCard.Padding = New-Object Windows.Forms.Padding(14,14,14,10)
$bottomCard.BorderStyle = 'None'
$layout.Controls.Add($bottomCard,0,3)

$bottomLayout = New-Object Windows.Forms.TableLayoutPanel
$bottomLayout.Dock = 'Fill'
$bottomLayout.ColumnCount = 1
$bottomLayout.RowCount = 2
$bottomLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Percent',100))) | Out-Null
$bottomLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle('Absolute',28))) | Out-Null
$bottomCard.Controls.Add($bottomLayout)

$log = New-TextBox
$log.BackColor = $surfaceAlt
$log.Font = New-Object Drawing.Font('Consolas',10)
$bottomLayout.Controls.Add($log,0,0)

$status = New-Object Windows.Forms.Label
$status.Dock = 'Fill'
$status.Padding = New-Object Windows.Forms.Padding(4,6,0,0)
$status.Text = '● READY   |   LOCAL / OFFLINE   |   SOURCE UNMODIFIED'
$status.ForeColor = $accentTeal
$status.Font = New-Object Drawing.Font('Microsoft YaHei UI',10,[Drawing.FontStyle]::Bold)
$bottomLayout.Controls.Add($status,0,1)
function Log-Line([string]$message) {
    $line='['+(Get-Date -Format 'HH:mm:ss')+'] '+$message+"`r`n"
    $log.AppendText($line)
    try { [IO.File]::AppendAllText($script:StartupLog,$line,[Text.Encoding]::UTF8) } catch {}
}
function Show-Error([string]$message) { Log-Line $message;[Windows.Forms.MessageBox]::Show($form,$message,'操作未完成','OK','Error') | Out-Null }
function Need-Source {
    if (-not $script:Source) { Show-Error '请先载入固件。';return $false };return $true
}
function Selected-Name {
    if ($grid.SelectedRows.Count -eq 0) {throw '请先在分区表中选择一项。'}
    return [string]$grid.SelectedRows[0].Cells['name'].Value
}
function Request-Base([string]$action) {
    return @{action=$action;source=$script:Source;expected_sha256=$script:Info.bin_sha256}
}
function Open-File([string]$filter) {
    $d=New-Object Windows.Forms.OpenFileDialog;$d.Filter=$filter
    try {if ($d.ShowDialog($form) -eq 'OK') {return $d.FileName};return $null} finally {$d.Dispose()}
}
function Save-File([string]$name,[string]$filter) {
    $d=New-Object Windows.Forms.SaveFileDialog;$d.FileName=$name;$d.Filter=$filter;$d.OverwritePrompt=$true
    try {if ($d.ShowDialog($form) -eq 'OK') {return $d.FileName};return $null} finally {$d.Dispose()}
}
function Pick-Folder([string]$title) {
    $d=New-Object Windows.Forms.FolderBrowserDialog;$d.Description=$title
    try {if ($d.ShowDialog($form) -eq 'OK') {return $d.SelectedPath};return $null} finally {$d.Dispose()}
}
function Refresh-Stage {
    foreach ($row in $grid.Rows) {
        $name=[string]$row.Cells['name'].Value
        $row.Cells['stage'].Value=if ($script:Replacements.ContainsKey($name)) {'已暂存'} else {'原始'}
    }
}
function Show-Info($info) {
    $script:Info=$info
    $o=$info.outer
    $overview.Text=@"
配置：$($info.profile)
源文件：$($script:Source)
源文件大小：$($info.source.file_size) B
源文件 MD5：$($info.source.file_md5)
源文件 SHA-256：$($info.source.file_sha256)

BIN 大小：$($info.bin_size) B
BIN MD5：$($info.bin_md5)
BIN SHA-256：$($info.bin_sha256)

外层标记：$($o.magic)
软件版本：$($o.software)
SDK 版本：$($o.sdk)
内层名称：$($o.inner_name)
外层头：$($o.header_size) B
载荷：$($o.payload_size) B
外层存储 MD5：$($o.stored_md5)
主脚本偏移：$('0x{0:X}' -f [long]$o.main_script_offset)

version_info 原文：
$($o.version_info)

权限基准：当前载入文件。所有更改仅暂存；打包另存。
"@ -replace "`n","`r`n"
    $overviewFacts.BeginUpdate()
    try {
        $overviewFacts.Items.Clear()
        Set-OverviewFact '文件' ([IO.Path]::GetFileName($script:Source))
        Set-OverviewFact '固件配置' ([string]$info.profile)
        Set-OverviewFact '软件版本' ([string]$o.software)
        Set-OverviewFact 'SDK 版本' ([string]$o.sdk)
        Set-OverviewFact '源文件大小' ([string]$info.source.file_size + ' B')
        Set-OverviewFact 'BIN 大小' ([string]$info.bin_size + ' B')
        Set-OverviewFact '外层标记' ([string]$o.magic)
        Set-OverviewFact '分区数量' ([string]@($info.partitions).Count)
        Set-OverviewFact '校验项目' ([string]@($info.verification.checks).Count)
        Set-OverviewFact '外层头长度' ([string]$o.header_size + ' B')
        Set-OverviewFact '载荷长度' ([string]$o.payload_size + ' B')
        Set-OverviewFact '内层名称' ([string]$o.inner_name)
        Set-OverviewFact '操作方式' '源文件不变 / 输出另存'
    } finally { $overviewFacts.EndUpdate() }
    $fileLabel.Text='●  当前源文件：' + $script:Source
    $grid.Rows.Clear()
    foreach ($p in $info.partitions) {
        $grid.Rows.Add([object[]]@($p.name,('0x{0:X}' -f [long]$p.offset),('0x{0:X}' -f [long]$p.relative_offset),$p.length,('0x{0:X}' -f [long]$p.flash_offset),$p.capacity,$p.kind,$p.md5,'原始')) | Out-Null
    }
    $checks.Items.Clear()
    foreach ($c in $info.verification.checks) {
        $item=New-Object Windows.Forms.ListViewItem([string]$c.status)
        $item.SubItems.Add([string]$c.name) | Out-Null;$item.SubItems.Add([string]$c.detail) | Out-Null
        $item.ForeColor=switch ($c.status) {'PASS' {$accentTeal};'FAIL' {$errorColor};default {$warning}}
        $checks.Items.Add($item) | Out-Null
    }
    Refresh-Stage
    Update-SquashPartitions
    $failed=@($info.verification.checks | Where-Object status -eq 'FAIL').Count
    Log-Line ('读取完成：19 个分区；'+$info.verification.checks.Count+' 项检查；失败 '+$failed+' 项。厂商封装状态见黄色提示。')
}
function Reset-TaskUi {
    foreach ($b in $script:Buttons) { $b.Enabled=$true }
    $form.UseWaitCursor=$false
    $grid.UseWaitCursor=$false
    $grid.Cursor=[Windows.Forms.Cursors]::Default
    $partitionMenu.UseWaitCursor=$false
    $partitionMenu.Cursor=[Windows.Forms.Cursors]::Default
    $squashWorkspace.UseWaitCursor=$false
    $squashWorkspace.Cursor=[Windows.Forms.Cursors]::Default
    [Windows.Forms.Cursor]::Current=[Windows.Forms.Cursors]::Default
    $status.Text='● READY   |   LOCAL / OFFLINE   |   WAITING FOR NEXT ACTION'
}
function Start-Task([hashtable]$request,[scriptblock]$onSuccess,[string]$message) {
    if ($script:Pending) {return}
    $dir=$null
    $proc=$null
    try {
        $dir=Join-Path $script:TempRoot ([Guid]::NewGuid().ToString('N'))
        [IO.Directory]::CreateDirectory($dir) | Out-Null
        $infile=Join-Path $dir 'request.json';$outfile=Join-Path $dir 'result.json'
        [IO.File]::WriteAllText($infile,($request | ConvertTo-Json -Depth 40),(New-Object Text.UTF8Encoding($false)))
        $si=New-Object Diagnostics.ProcessStartInfo
        $si.FileName=$script:Python
        $si.Arguments='"'+$script:Engine+'" "'+$infile+'" "'+$outfile+'"'
        $si.UseShellExecute=$false;$si.CreateNoWindow=$true;$si.WorkingDirectory=$script:HomeDir
        $si.RedirectStandardError=$true
        $proc=New-Object Diagnostics.Process;$proc.StartInfo=$si
        if (-not $proc.Start()) {throw 'Python 后端进程启动失败。'}
        $script:Pending=@{process=$proc;result=$outfile;callback=$onSuccess;dir=$dir;stderr=$proc.StandardError.ReadToEndAsync()}
        foreach ($b in $script:Buttons) { $b.Enabled=$false }
        $status.Text=$message;$form.UseWaitCursor=$true;Log-Line $message
    } catch {
        $script:Pending=$null
        Reset-TaskUi
        if ($proc) { $proc.Dispose() }
        if ($dir -and (Test-Path -LiteralPath $dir)) { Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue }
        Show-Error ('任务启动失败：'+$_.Exception.Message)
    }
}
$timer=New-Object Windows.Forms.Timer;$timer.Interval=250
$timer.Add_Tick({
    if ($script:Pending) {
        $job=$script:Pending
        if ($job.process.HasExited) {
            $script:Pending=$null
            try {
                $backendError=[string]$job.stderr.Result
                if ($backendError) {Log-Line ('后端诊断：'+$backendError)}
                if (-not (Test-Path -LiteralPath $job.result)) {throw ('后端未返回结果，退出码：'+$job.process.ExitCode+'。请检查解压是否完整。')}
                $result=[IO.File]::ReadAllText($job.result,[Text.Encoding]::UTF8) | ConvertFrom-Json
                if (-not $result.success) {if ($result.traceback) {Log-Line ([string]$result.traceback)};throw $result.error}
                & $job.callback $result.data
            } catch { Show-Error $_.Exception.Message }
            finally {
                try { $job.process.Dispose() } catch {}
                try { Remove-Item -LiteralPath $job.dir -Recurse -Force -ErrorAction SilentlyContinue } catch {}
                Reset-TaskUi
            }
        }
    }
})
$timer.Start()

$loadButton=New-Button '载入固件' {
    try {
        $path=Open-File '固件文件 (*.bin;*.zip)|*.bin;*.zip|所有文件 (*.*)|*.*'
        if (-not $path) {return}
        $script:LoadingPath=$path
        $callback={param($data) $script:Source=$script:LoadingPath;$script:Replacements=@{};Show-Info $data;$tabs.SelectedTab=$overviewTab}
        Start-Task @{action='inspect';source=$path} $callback '正在读取并校验固件…'
    } catch {Show-Error $_.Exception.Message}
}
$loadButton.BackColor=$accentTeal;$loadButton.ForeColor=[Drawing.Color]::White;$loadButton.FlatAppearance.BorderColor=$accentTeal;$loadButton.Tag='primary'
$null=New-Button '全部分割' {
    if (-not (Need-Source)) {return}
    try {$dir=Pick-Folder '选择空目录以分割全部分区';if (-not $dir) {return};$r=Request-Base 'export_all';$r.directory=$dir
        Start-Task $r {param($d) Log-Line ('分割完成：'+$d.directory);[Windows.Forms.MessageBox]::Show($form,'已导出 19 个分区、脚本和权限清单。','完成') | Out-Null} '正在分割并导出清单…'
    } catch {Show-Error $_.Exception.Message}
}
$exportSelectedButton=New-Button '导出选中' {
    if (-not (Need-Source)) {return}
    try {$name=Selected-Name;$path=Save-File ($name+'.bin') '分区镜像 (*.bin)|*.bin';if (-not $path) {return};$r=Request-Base 'export_one';$r.name=$name;$r.output=$path
        Start-Task $r {param($d) Log-Line ('已导出：'+$d.output)} '正在导出原始分区…'
    } catch {Show-Error $_.Exception.Message}
}
Add-ToolSeparator
$importSelectedButton=New-Button '导入选中' {
    if (-not (Need-Source)) {return}
    try {$name=Selected-Name;$path=Open-File '分区镜像 (*.*)|*.*';if (-not $path) {return};$r=Request-Base 'import';$r.name=$name;$r.path=$path
        Start-Task $r {param($d) $script:Replacements[$d.name]=@{path=$d.path;sha256=$d.sha256};Refresh-Stage;Log-Line ('已暂存 '+$d.name+'；补零 '+$d.padding+' B；权限对比 '+$d.permission_comparison)} '正在核对导入分区及 Linux 权限…'
    } catch {Show-Error $_.Exception.Message}
}
$extractSquashButton=New-Button '解包 SquashFS' {
    if (-not (Need-Source)) {return}
    try {
        $name=Selected-SquashName
        $dir=Pick-Folder '请选择空目录以解包选中 SquashFS 分区'
        if (-not $dir) {return}
        $r=Request-Base 'extract_squashfs';$r.name=$name;$r.directory=$dir
        Start-Task $r {param($d)
            Log-Line ('解包完成：'+$d.files+' 个普通文件；已记录待恢复的 Unix 专用节点 '+$d.skipped+' 项。')
            Log-Line ('元数据清单：'+$d.metadata)
            [Windows.Forms.MessageBox]::Show($form,'解包完成，元数据清单已输出到解包目录旁边。重建前请保留该 JSON 文件。','SquashFS 解包完成') | Out-Null
        } '正在解包 SquashFS 文件与元数据清单…'
    } catch {Show-Error $_.Exception.Message}
} 120
$rebuildFolderButton=New-Button '目录重建' {
    if (-not (Need-Source)) {return}
    try {
        $name=Selected-SquashName
        $dir=Pick-Folder '选择待重建的 Windows 解压目录'
        if (-not $dir) {return}
        $dest=Save-File ($name+'_rebuilt.squashfs') 'SquashFS 镜像 (*.squashfs)|*.squashfs|所有文件 (*.*)|*.*'
        if (-not $dest) {return}
        $r=Request-Base 'rebuild_directory';$r.name=$name;$r.directory=$dir;$r.output=$dest
        Start-Task $r {param($d)
            $script:Replacements[$d.name]=@{path=$d.path;sha256=$d.sha256}
            Refresh-Stage
            if ($d.unchanged) {Log-Line '工作目录内容未修改，已按原始字节导出，避免无意义重压缩。'}
            Log-Line ('SquashFS 目录重建并验证通过：'+$d.path)
        } '正在重建 SquashFS，并检查槽位/权限/元数据…'
    } catch {Show-Error $_.Exception.Message}
} 112
# Move SquashFS-specific buttons out of firmware toolbar into a dedicated page.
foreach ($b in @($extractSquashButton,$rebuildFolderButton)) {
    $toolbar.Controls.Remove($b)
    $b.Width=[Math]::Max($b.Width,190)
    $squashActions.Controls.Add($b)
}
$undoSelectedButton=New-Button '撤销选中' {
    try {$name=Selected-Name;$null=$script:Replacements.Remove($name);Refresh-Stage;Log-Line ('已撤销暂存：'+$name)} catch {Show-Error $_.Exception.Message}
}
$null=New-Button '导入工程' {
    if (-not (Need-Source)) {return}
    try {$dir=Pick-Folder '选择含 project.json 的分割目录';if (-not $dir) {return};$r=Request-Base 'import_folder';$r.directory=$dir
        Start-Task $r {param($d) $script:Replacements=@{};foreach ($p in $d.PSObject.Properties) {$script:Replacements[$p.Name]=@{path=$p.Value.path;sha256=$p.Value.sha256}};Refresh-Stage;Log-Line '工程分区已全部核对并暂存。'} '正在核对工程及所有导入分区…'
    } catch {Show-Error $_.Exception.Message}
}
Add-ToolSeparator
$permissionsButton=New-Button '权限清单' {
    if (-not (Need-Source)) {return}
    try {$name=Selected-Name;$r=Request-Base 'permissions';$r.name=$name
        Start-Task $r {param($d) $permissions.Text=($d | ConvertTo-Json -Depth 30);$tabs.SelectedTab=$permissionsTab;Log-Line ('权限清单：'+$d.name+' / '+$d.paths+' 条路径')} '正在读取 Linux 文件系统元数据…'
    } catch {Show-Error $_.Exception.Message}
}
$null=New-Button '深度校验' {
    if (-not (Need-Source)) {return}
    $r=Request-Base 'verify';$r.deep=$true
    Start-Task $r {param($d) Show-Info $d;$tabs.SelectedTab=$checksTab} '正在解压校验全部文件，可能需要数分钟…'
}
function Pack-Firmware([bool]$zip) {
    if (-not (Need-Source)) {return}
    try {
        $name=if ($zip) {'AE5i_REPACKED.zip'} else {'GEMINI_PACK_REPACKED.BIN'}
        $filter=if ($zip) {'固件 ZIP (*.zip)|*.zip'} else {'固件 BIN (*.bin)|*.bin'}
        $path=Save-File $name $filter;if (-not $path) {return}
        $r=Request-Base 'build';$r.output=$path;$r.replacements=$script:Replacements
        Start-Task $r {param($d) Log-Line ('打包成功：'+$d.output);Log-Line ('输出 SHA-256：'+$d.output_sha256)
            [Windows.Forms.MessageBox]::Show($form,('已打包并回读校验。'+"`r`n"+$d.output+"`r`n`r`n"+'权限与源固件一致；校验报告已保存为 .report.json。'+"`r`n"+'厂商 uboot 封装原样保留，内部算法未验证。'),'完成','OK','Information') | Out-Null
        } '正在更新各层校验、检查权限并打包…'
    } catch {Show-Error $_.Exception.Message}
}
Add-ToolSeparator
$null=New-Button '打包 BIN' {Pack-Firmware $false} 92
$null=New-Button '打包 ZIP' {Pack-Firmware $true} 92
$form.Add_FormClosing({param($sender,$e) if ($script:Pending) {$e.Cancel=$true;Log-Line '当前任务尚未结束，请等待后关闭。'}})
$form.Add_FormClosed({try { [IO.File]::AppendAllText($script:StartupLog, "UI FormClosed`r`n") } catch {}; $timer.Stop();$timer.Dispose();Remove-Item -LiteralPath $script:TempRoot -Recurse -Force -ErrorAction SilentlyContinue})
Log-Line 'AE5i Firmware Studio 1.4.11 已就绪；界面已切换为统一工作台布局。'
Log-Line ('诊断日志：'+$script:StartupLog)
try { [IO.File]::AppendAllText($script:StartupLog,"UI initialized successfully`r`n") } catch {}
try {
    [Windows.Forms.Application]::Run($form)
    [IO.File]::AppendAllText($script:StartupLog, "Application.Run returned normally`r`n")
} catch {
    try { [IO.File]::AppendAllText($script:StartupLog, "Application.Run EXCEPTION: $($_.Exception.ToString())`r`n") } catch {}
    throw
}
