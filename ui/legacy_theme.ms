-- Shared presentation helpers; no scene operations.
global LXLegacyColor
global LXLegacyHeader
global LXLegacyPrimary
global LXLegacyDisposeHeader
global LXLegacyText
global LXLegacySection
global LXLegacySecondary

fn LXLegacyColor r g b = (dotNetClass "System.Drawing.Color").FromArgb r g b

fn LXLegacyHeader panel title subtitle iconPath =
(
    panel.BackColor = LXLegacyColor 232 241 222
    local picture = dotNetObject "System.Windows.Forms.PictureBox"
    picture.Location = dotNetObject "System.Drawing.Point" 8 8
    picture.Size = dotNetObject "System.Drawing.Size" 48 48
    picture.SizeMode = (dotNetClass "System.Windows.Forms.PictureBoxSizeMode").Zoom
    if doesFileExist iconPath do
    (
        local original = (dotNetClass "System.Drawing.Image").FromFile iconPath
        picture.Image = original.Clone()
        original.Dispose()
    )
    panel.Controls.Add picture
    local heading = dotNetObject "System.Windows.Forms.Label"
    heading.Text = title
    heading.Location = dotNetObject "System.Drawing.Point" 68 6
    heading.Size = dotNetObject "System.Drawing.Size" 314 27
    heading.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 12.0 ((dotNetClass "System.Drawing.FontStyle").Bold)
    heading.ForeColor = LXLegacyColor 64 91 43
    panel.Controls.Add heading
    local description = dotNetObject "System.Windows.Forms.Label"
    description.Text = subtitle
    description.Location = dotNetObject "System.Drawing.Point" 69 34
    description.Size = dotNetObject "System.Drawing.Size" 313 24
    description.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 8.5
    description.ForeColor = LXLegacyColor 83 101 67
    panel.Controls.Add description
)

fn LXLegacyPrimary control caption =
(
    control.Text = caption
    control.FlatStyle = (dotNetClass "System.Windows.Forms.FlatStyle").Flat
    control.FlatAppearance.BorderSize = 0
    control.BackColor = LXLegacyColor 111 148 74
    control.ForeColor = LXLegacyColor 255 255 255
    control.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 10.0 ((dotNetClass "System.Drawing.FontStyle").Bold)
    control.UseVisualStyleBackColor = false
)

fn LXLegacyText control =
(
    control.BackColor = LXLegacyColor 248 250 245
    control.ForeColor = LXLegacyColor 48 61 42
    control.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 9.0
    if (control.GetType()).FullName == "System.Windows.Forms.Label" do
    (
        control.AutoEllipsis = true
        control.TextAlign = (dotNetClass "System.Drawing.ContentAlignment").MiddleLeft
    )
)

fn LXLegacySection control =
(
    control.BackColor = LXLegacyColor 232 241 222
    control.ForeColor = LXLegacyColor 64 91 43
    control.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 9.0 ((dotNetClass "System.Drawing.FontStyle").Bold)
    control.TextAlign = (dotNetClass "System.Drawing.ContentAlignment").MiddleLeft
    control.Padding = dotNetObject "System.Windows.Forms.Padding" 8 0 0 0
)

fn LXLegacySecondary control caption =
(
    LXLegacyPrimary control caption
    control.BackColor = LXLegacyColor 230 237 222
    control.ForeColor = LXLegacyColor 55 78 39
    control.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 9.0
)

fn LXLegacyDisposeHeader panel =
(
    try
    (
        for control in panel.Controls do
        (
            if (control.GetType()).FullName == "System.Windows.Forms.PictureBox" do
                if control.Image != undefined do control.Image.Dispose()
        )
    ) catch()
)
