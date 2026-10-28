// AirFare.exe: the icon people double-click. On a PC where AirFare isn't set up yet it offers to run the
// installer; after that it opens AirFare Settings. The Startup shortcut runs "AirFare.exe --service", so
// Windows lists the startup entry as AirFare with this icon instead of as Python. It also opens airfare:
// links (see airfare\links.py), which notifications and pages opened from disk use to reach the live pages.
//
// Built with the C# compiler that ships with Windows (C# 5): see launcher\build.ps1.
using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Windows.Forms;

[assembly: AssemblyTitle("AirFare")]
[assembly: AssemblyDescription("AirFare flight price watcher")]
[assembly: AssemblyProduct("AirFare")]
[assembly: AssemblyCompany("AirFare")]
[assembly: AssemblyCopyright("")]
[assembly: AssemblyVersion("1.4.1.0")]
[assembly: AssemblyFileVersion("1.4.1.0")]

static class Launcher
{
    const string Title = "AirFare";
    static string lang = "en";

    // The language picked in AirFare Settings; before setup, Windows' display language.
    static string Language(string root)
    {
        try
        {
            string config = File.ReadAllText(Path.Combine(root, @"data\config.json"));
            Match m = Regex.Match(config, "\"language\"\\s*:\\s*\"(en|es|ru)\"");
            if (m.Success)
                return m.Groups[1].Value;
        }
        catch (Exception) { }
        string ui = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName;
        return ui == "es" || ui == "ru" ? ui : "en";
    }

    static string T(string en, string es, string ru)
    {
        return lang == "es" ? es : lang == "ru" ? ru : en;
    }

    [STAThread]
    static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
        string scripts = Path.Combine(root, @".venv\Scripts");
        string python = Path.Combine(scripts, "python.exe");
        string pythonw = Path.Combine(scripts, "pythonw.exe");
        lang = Language(root);
        string mode = args.Length > 0 ? args[0].TrimStart('-', '/').ToLowerInvariant() : "settings";
        bool link = mode.StartsWith("airfare:");
        if (link)
        {
            // airfare:dashboard, airfare://dashboard/ and the like. Any web page can offer such a link, so
            // only these four names do anything, and nothing from the link reaches Python.
            mode = mode.Substring(8).Trim('/');
            int cut = mode.IndexOfAny(new char[] { '/', '?', '#' });
            if (cut >= 0)
                mode = mode.Substring(0, cut);
            if (mode != "dashboard" && mode != "history" && mode != "settings" && mode != "start")
                return 2;
        }

        if (mode == "install")
            return Install(root, true);
        if (!File.Exists(python))
        {
            // Only a plain double-click offers setup. The Startup entry and the installer itself pass an
            // option, so a broken setup can never start the installer again and again.
            if (args.Length == 0)
                return Install(root, false);
            if (mode != "service")
                MessageBox.Show(T("AirFare's Python environment is missing from ",
                                  "Falta el entorno de Python de AirFare en ",
                                  "Не найдено окружение Python для AirFare в ") + scripts + ".\n\n" +
                                T("Run AirFare.exe --install to set it up again.",
                                  "Ejecuta AirFare.exe --install para instalarlo de nuevo.",
                                  "Запустите AirFare.exe --install, чтобы установить его заново."),
                                Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        string command;
        switch (mode)
        {
            case "service": command = "service"; break;
            case "check": command = "run"; break;
            case "settings": command = "setup"; break;
            case "dashboard": command = "setup --page dashboard"; break;
            case "history": command = "setup --page history"; break;
            case "start": command = "setup --no-open"; break;   // the page that opened the link moves on by itself
            default:
                MessageBox.Show(T("Unknown option: ", "Opción desconocida: ", "Неизвестный параметр: ") + args[0] +
                                "\n\n--settings, --dashboard, --history, --check, --service, --install",
                                Title, MessageBoxButtons.OK, MessageBoxIcon.Information);
                return 2;
        }
        // pythonw runs without a console window; python.exe does the same job with its console hidden.
        bool windowless = File.Exists(pythonw);
        return Start(windowless ? pythonw : python, "-m airfare " + command, root, !windowless) ? 0 : 1;
    }

    static int Install(string root, bool asked)
    {
        string script = Path.Combine(root, "install.ps1");
        if (!File.Exists(script))
        {
            MessageBox.Show(T("install.ps1 is missing from ", "Falta install.ps1 en ", "Не найден install.ps1 в ") + root + ".\n\n" +
                            T("Unzip the whole AirFare folder and try again.",
                              "Descomprime la carpeta AirFare completa y vuelve a intentarlo.",
                              "Распакуйте папку AirFare целиком и попробуйте снова."),
                            Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        if (!asked)
        {
            DialogResult answer = MessageBox.Show(T(
                "AirFare isn't set up on this PC yet.\n\nSet it up now? It takes about 5 minutes and needs the internet. " +
                "A window shows the progress, and AirFare Settings opens when it's done.",
                "AirFare aún no está instalado en este PC.\n\n¿Instalarlo ahora? Tarda unos 5 minutos y necesita internet. " +
                "Una ventana muestra el progreso y, al terminar, se abren los Ajustes de AirFare.",
                "AirFare ещё не установлен на этом ПК.\n\nУстановить сейчас? Это займёт около 5 минут и нужен интернет. " +
                "В окне будет виден ход установки, а по завершении откроются настройки AirFare."),
                Title, MessageBoxButtons.OKCancel, MessageBoxIcon.Information);
            if (answer != DialogResult.OK)
                return 0;
        }
        string powershell = Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\powershell.exe");
        ProcessStartInfo info = new ProcessStartInfo(powershell,
            "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\"");
        info.WorkingDirectory = root;
        info.UseShellExecute = true;   // its own console window, so the progress is visible
        try
        {
            Process.Start(info);
            return 0;
        }
        catch (Exception e)
        {
            MessageBox.Show(T("Couldn't start the installer: ", "No se pudo iniciar el instalador: ",
                              "Не удалось запустить установщик: ") + e.Message, Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static bool Start(string exe, string arguments, string root, bool hideConsole)
    {
        ProcessStartInfo info = new ProcessStartInfo(exe, arguments);
        info.WorkingDirectory = root;
        info.UseShellExecute = false;
        info.CreateNoWindow = hideConsole;
        try
        {
            Process.Start(info);
            return true;
        }
        catch (Exception e)
        {
            MessageBox.Show(T("Couldn't start AirFare: ", "No se pudo iniciar AirFare: ", "Не удалось запустить AirFare: ") +
                            e.Message + "\n\n" + T("Run AirFare.exe --install to repair it.",
                                                    "Ejecuta AirFare.exe --install para repararlo.",
                                                    "Запустите AirFare.exe --install, чтобы исправить."),
                            Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return false;
        }
    }
}
