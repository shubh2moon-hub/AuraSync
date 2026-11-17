using GHelper.UI;
using System.Diagnostics;
using System.Text;

namespace GHelper
{
    // Wallpaper and phone controls for the AuraSync engine, inside G-Helper.
    // AuraSync (a small native app) draws the desktop wallpaper and syncs the phone; this window only
    // edits its settings file, which AuraSync watches. G-Helper keeps control of the keyboard.
    public class WallpaperForm : RForm
    {
        static readonly string Dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "AuraSync");
        static readonly string Ini = Path.Combine(Dir, "settings.ini");
        static readonly string PairFile = Path.Combine(Dir, "pair.txt");

        static readonly string[] Effects = { "Static", "Breathe", "Color Cycle", "Strobe", "Rainbow", "Comet" };
        static readonly string[] Speeds = { "Slow", "Normal", "Fast" };
        static readonly Color[] Swatches = {
            Color.FromArgb(255, 42, 58), Color.FromArgb(255, 106, 0), Color.FromArgb(255, 212, 0),
            Color.FromArgb(43, 255, 136), Color.FromArgb(0, 229, 255), Color.FromArgb(61, 123, 255),
            Color.FromArgb(122, 92, 255), Color.FromArgb(255, 47, 180), Color.White };

        readonly FlowLayoutPanel root = new() { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true, Padding = new Padding(16) };
        readonly FlowLayoutPanel grid = new() { Width = 760, Height = 330, AutoScroll = true };
        readonly Label status = new() { AutoSize = true };
        readonly List<Image> thumbs = new();

        public WallpaperForm()
        {
            Text = "AuraSync – wallpaper and phone";
            Size = new Size(820, 760);
            StartPosition = FormStartPosition.CenterScreen;
            Controls.Add(root);
            Build();
            InitTheme(true);
            FormClosed += (s, e) => { foreach (var t in thumbs) t.Dispose(); thumbs.Clear(); };
        }

        Label Heading(string t) => new() { Text = t.ToUpper(), AutoSize = true, Font = new Font(Font.FontFamily, 8.5f, FontStyle.Bold), Margin = new Padding(0, 14, 0, 6) };

        RButton Btn(string t, bool selected, Action onClick)
        {
            var b = new RButton { Text = t, AutoSize = true, Height = 32, Margin = new Padding(0, 0, 6, 6), Secondary = !selected };
            b.FlatAppearance.BorderSize = selected ? 2 : 1;
            b.Click += (s, e) => { onClick(); Build(); };
            return b;
        }

        void Build()
        {
            root.SuspendLayout();
            root.Controls.Clear();
            foreach (var t in thumbs) t.Dispose();
            thumbs.Clear();

            string exe = AppConfig.GetString("aurasync_exe") ?? "";
            bool running = Process.GetProcessesByName("AuraSync").Length > 0;
            status.Text = running ? "AuraSync is running." : File.Exists(exe) ? "AuraSync is not running." : "AuraSync not found. Locate AuraSync.exe.";
            root.Controls.Add(status);

            var top = new FlowLayoutPanel { AutoSize = true, WrapContents = false };
            if (!running && File.Exists(exe)) top.Controls.Add(Btn("Start AuraSync", false, StartAuraSync));
            top.Controls.Add(Btn("Locate AuraSync.exe…", false, Locate));
            root.Controls.Add(top);

            // wallpapers
            root.Controls.Add(Heading("Wallpaper"));
            grid.Controls.Clear();
            string current = Get("pack", "");
            string? packsDir = PacksDir(exe);
            if (packsDir != null)
                foreach (var d in Directory.GetDirectories(packsDir).OrderBy(x => x))
                {
                    string id = Path.GetFileName(d), prev = Path.Combine(d, "pc_preview.jpg");
                    if (!File.Exists(prev)) continue;
                    grid.Controls.Add(Card(id, PackName(d) ?? id, prev, id == current));
                }
            root.Controls.Add(grid);

            // lighting (wallpaper and phone; the keyboard stays with G-Helper)
            root.Controls.Add(Heading("Wallpaper lighting"));
            int effect = int.TryParse(Get("effect", "4"), out var ef) ? ef : 4;
            var row = new FlowLayoutPanel { AutoSize = true };
            for (int i = 0; i < Effects.Length; i++) { int k = i; row.Controls.Add(Btn(Effects[i], effect == i, () => Set("effect", k.ToString()))); }
            root.Controls.Add(row);

            int speed = int.TryParse(Get("speed", "1"), out var sp) ? sp : 1;
            var srow = new FlowLayoutPanel { AutoSize = true };
            for (int i = 0; i < Speeds.Length; i++) { int k = i; srow.Controls.Add(Btn(Speeds[i], speed == i, () => Set("speed", k.ToString()))); }
            root.Controls.Add(srow);

            var crow = new FlowLayoutPanel { AutoSize = true };
            foreach (var c in Swatches)
            {
                var sw = new Button { BackColor = c, Width = 30, Height = 30, FlatStyle = FlatStyle.Flat, Margin = new Padding(0, 0, 6, 6) };
                sw.Click += (s, e) => { Set("color", ToColorRef(c).ToString()); Build(); };
                crow.Controls.Add(sw);
            }
            crow.Controls.Add(Btn("Custom…", false, PickColor));
            root.Controls.Add(crow);

            // phone
            root.Controls.Add(Heading("Phone"));
            string code = File.Exists(PairFile) ? File.ReadAllText(PairFile).Trim() : "";
            root.Controls.Add(new Label
            {
                AutoSize = true,
                Text = code.Length == 10
                    ? $"Pairing code: {code[..5]}-{code[5..]}   (type it in the AuraSync phone app)"
                    : "Start AuraSync once to create a pairing code."
            });
            root.ResumeLayout();
        }

        Control Card(string id, string name, string preview, bool selected)
        {
            var img = Thumb(preview, 168, 94);
            var card = new Panel { Width = 180, Height = 130, Margin = new Padding(0, 0, 8, 8), BorderStyle = selected ? BorderStyle.FixedSingle : BorderStyle.None, Cursor = Cursors.Hand };
            var pic = new PictureBox { Image = img, Width = 168, Height = 94, Left = 6, Top = 6, SizeMode = PictureBoxSizeMode.Zoom };
            var lbl = new Label { Text = name, Left = 6, Top = 104, Width = 168, Height = 20, TextAlign = ContentAlignment.MiddleCenter, AutoEllipsis = true };
            card.Controls.Add(pic); card.Controls.Add(lbl);
            EventHandler pick = (s, e) => { Set("pack", id); Build(); };
            card.Click += pick; pic.Click += pick; lbl.Click += pick;
            return card;
        }

        // Decodes a small copy and frees the full-size image straight away.
        Image Thumb(string path, int w, int h)
        {
            using var full = Image.FromFile(path);
            var small = new Bitmap(w, h);
            using (var g = Graphics.FromImage(small)) g.DrawImage(full, 0, 0, w, h);
            thumbs.Add(small);
            return small;
        }

        static string? PacksDir(string exe)
        {
            if (!File.Exists(exe)) return null;
            string dir = Path.GetDirectoryName(exe)!;
            foreach (var rel in new[] { "library\\packs", "..\\library\\packs", "..\\..\\library\\packs" })
            {
                string p = Path.GetFullPath(Path.Combine(dir, rel));
                if (Directory.Exists(p)) return p;
            }
            return null;
        }

        static string? PackName(string dir)
        {
            try
            {
                string json = File.ReadAllText(Path.Combine(dir, "meta.json"));
                int i = json.IndexOf("\"name\""); if (i < 0) return null;
                int a = json.IndexOf('"', json.IndexOf(':', i) + 1), b = json.IndexOf('"', a + 1);
                return json.Substring(a + 1, b - a - 1);
            }
            catch { return null; }
        }

        static int ToColorRef(Color c) => c.R | (c.G << 8) | (c.B << 16);   // Windows COLORREF, as AuraSync stores it

        void PickColor()
        {
            using var dlg = new ColorDialog { FullOpen = true };
            if (dlg.ShowDialog(this) == DialogResult.OK) Set("color", ToColorRef(dlg.Color).ToString());
        }

        void Locate()
        {
            using var dlg = new OpenFileDialog { Filter = "AuraSync.exe|AuraSync.exe", Title = "Locate AuraSync.exe" };
            if (dlg.ShowDialog(this) == DialogResult.OK) AppConfig.Set("aurasync_exe", dlg.FileName);
        }

        public static void StartAuraSync()
        {
            string exe = AppConfig.GetString("aurasync_exe") ?? "";
            if (!File.Exists(exe) || Process.GetProcessesByName("AuraSync").Length > 0) return;
            Set("keyboard", "0");   // G-Helper owns the keyboard
            Process.Start(new ProcessStartInfo(exe) { WorkingDirectory = Path.GetDirectoryName(exe)!, UseShellExecute = true });
        }

        // ---- settings.ini ([AuraSync] key=value); AuraSync reloads it when it changes

        static string Get(string key, string def)
        {
            if (!File.Exists(Ini)) return def;
            foreach (var line in File.ReadAllLines(Ini))
                if (line.StartsWith(key + "=")) return line[(key.Length + 1)..].Trim();
            return def;
        }

        static void Set(string key, string value)
        {
            Directory.CreateDirectory(Dir);
            var lines = File.Exists(Ini) ? File.ReadAllLines(Ini).ToList() : new List<string> { "[AuraSync]" };
            if (!lines.Any(l => l.Trim() == "[AuraSync]")) lines.Insert(0, "[AuraSync]");
            int i = lines.FindIndex(l => l.StartsWith(key + "="));
            if (i >= 0) lines[i] = key + "=" + value; else lines.Add(key + "=" + value);
            File.WriteAllLines(Ini, lines, new UTF8Encoding(false));
        }
    }
}
