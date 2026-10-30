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
    panel.BackColor = LXLegacyColor 47 57 41
    local picture = dotNetObject "System.Windows.Forms.PictureBox"
    picture.Location = dotNetObject "System.Drawing.Point" 10 10
    picture.Size = dotNetObject "System.Drawing.Size" 62 62
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
    heading.Location = dotNetObject "System.Drawing.Point" 84 13
    heading.Size = dotNetObject "System.Drawing.Size" 294 30
    heading.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 12.0 ((dotNetClass "System.Drawing.FontStyle").Bold)
    heading.ForeColor = LXLegacyColor 194 222 155
    panel.Controls.Add heading
    local description = dotNetObject "System.Windows.Forms.Label"
    description.Text = subtitle
    description.Location = dotNetObject "System.Drawing.Point" 85 47
    description.Size = dotNetObject "System.Drawing.Size" 292 28
    description.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 8.5
    description.ForeColor = LXLegacyColor 190 198 182
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
    control.BackColor = LXLegacyColor 39 44 37
    control.ForeColor = LXLegacyColor 211 221 201
    control.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 9.0
)

fn LXLegacySection control =
(
    control.BackColor = LXLegacyColor 47 57 41
    control.ForeColor = LXLegacyColor 194 222 155
    control.Font = dotNetObject "System.Drawing.Font" "Microsoft YaHei UI" 9.0 ((dotNetClass "System.Drawing.FontStyle").Bold)
    control.TextAlign = (dotNetClass "System.Drawing.ContentAlignment").MiddleLeft
    control.Padding = dotNetObject "System.Windows.Forms.Padding" 8 0 0 0
)

fn LXLegacySecondary control caption =
(
    LXLegacyPrimary control caption
    control.BackColor = LXLegacyColor 58 69 51
    control.ForeColor = LXLegacyColor 220 229 210
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
