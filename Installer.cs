using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Windows.Forms;
using Microsoft.Win32;

static class Installer
{
    [STAThread]
    static int Main(string[] args)
    {
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Gary");
        string app = Path.Combine(root, "App");
        string shortcut = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Gary.lnk");
#if UNINSTALLER
        return args.Length == 0 ? Uninstall(root, shortcut) : 2;
#else
        if (args.Length == 1 && args[0] == "--uninstall")
            return Uninstall(root, shortcut);
        if (args.Length != 0) return 2;
        if (Directory.Exists(app) || Directory.Exists(Path.Combine(root,"MaintenanceRuntime")) || File.Exists(shortcut) ||
            File.Exists(Path.Combine(root,"uninstall.pending")) || File.Exists(Path.Combine(root,"maintenance.active")) ||
            Directory.Exists(Path.Combine(root,"Uninstalled-App")))
        {
            MessageBox.Show("Une installation ou un raccourci Gary existe déjà. Ce candidat installe uniquement une nouvelle instance.", "Gary");
            return 2;
        }
        if (MessageBox.Show("Installer le candidat Gary pour ce compte Windows ?", "Gary", MessageBoxButtons.OKCancel) != DialogResult.OK)
            return 1;
        try
        {
            Directory.CreateDirectory(root);
            if ((File.GetAttributes(root) & FileAttributes.ReparsePoint) != 0) throw new IOException();
            CheckRegistrationOwner(root);
            string ownership = Path.Combine(root,"Gary.installation");
            if (File.Exists(ownership))
            {
                RequireOrdinary(ownership);
                if (File.ReadAllText(ownership)!="Gary.Windows.PerUser.v1\n") throw new IOException();
            }
            string uninstaller;
            using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("uninstaller.exe"))
                uninstaller = PlaceUninstaller(root,resource);
            string stage = Path.Combine(root, "stage-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(stage);
            using (Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
            using (ZipArchive zip = new ZipArchive(payload))
            {
                foreach (ZipArchiveEntry item in zip.Entries)
                {
                    string target = Path.GetFullPath(Path.Combine(stage, item.FullName));
                    if (!target.StartsWith(stage + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                        throw new IOException();
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    using (Stream input = item.Open())
                    using (FileStream output = new FileStream(target, FileMode.CreateNew))
                        input.CopyTo(output);
                }
            }
            File.Move(Path.Combine(stage, "Gary.pyw"), Path.Combine(root, "Gary.pyw"));
            Directory.Move(Path.Combine(stage, "MaintenanceRuntime"), Path.Combine(root, "MaintenanceRuntime"));
            Directory.Move(Path.Combine(stage, "App"), app);
            dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
            dynamic link = shell.CreateShortcut(shortcut);
            link.TargetPath = Path.Combine(root, @"MaintenanceRuntime\pythonw.exe");
            link.Arguments = "\"" + Path.Combine(root, "Gary.pyw") + "\" start";
            link.WorkingDirectory = root;
            link.IconLocation = Path.Combine(app, @"v5\scripts\gary.ico");
            link.Save();
            if (!File.Exists(ownership))
                using (var marker = new StreamWriter(File.Open(ownership,FileMode.CreateNew)))
                    marker.Write("Gary.Windows.PerUser.v1\n");
            Register(root,uninstaller);
            MessageBox.Show("Gary est installé. Ouvrez-le avec le raccourci du Bureau.", "Gary");
            return 0;
        }
        catch
        {
            MessageBox.Show("Installation interrompue. Les données utilisateur sont conservées. Consultez la notice avant une nouvelle tentative.", "Gary");
            return 3;
        }
#endif
    }

    const string RegistryPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\Gary.V5";
    const string UninstallGate = "gary-uninstall-v1";

    static void ClaimUninstallGate(string gate)
    {
        if (File.Exists(gate))
        {
            RequireOrdinary(gate);
            if (File.ReadAllText(gate)!=UninstallGate) throw new IOException();
            return;
        }
        using (var stream=File.Open(gate,FileMode.CreateNew))
        {
            byte[] bytes=System.Text.Encoding.ASCII.GetBytes(UninstallGate);
            stream.Write(bytes,0,bytes.Length);
            stream.Flush(true);
        }
    }

    internal static string PlaceUninstaller(string root, Stream resource)
    {
        RequireOrdinary(root);
        using (SHA256 sha = SHA256.Create())
        {
            string hash = BitConverter.ToString(sha.ComputeHash(resource)).Replace("-","");
            string parent = Path.Combine(root,"Uninstallers");
            Directory.CreateDirectory(parent);
            RequireOrdinary(parent);
            string directory = Path.Combine(parent,hash);
            Directory.CreateDirectory(directory);
            RequireOrdinary(directory);
            string exe = Path.Combine(directory,"Uninstall_Gary.exe");
            if (File.Exists(exe))
            {
                RequireOrdinary(exe);
                using (Stream input = File.OpenRead(exe))
                    if (BitConverter.ToString(sha.ComputeHash(input)).Replace("-","")!=hash) throw new IOException();
            }
            else
            {
                resource.Position=0;
                using (Stream output=File.Open(exe,FileMode.CreateNew))
                    resource.CopyTo(output);
            }
            return exe;
        }
    }

    static void CheckRegistrationOwner(string root)
    {
        using (RegistryKey key = Registry.CurrentUser.OpenSubKey(RegistryPath))
        {
            if (key == null) return;
            if (!String.Equals(key.GetValue("InstallLocation") as string,root,StringComparison.OrdinalIgnoreCase))
                throw new IOException();
            string command=key.GetValue("UninstallString") as string;
            if (command==null || command.Length<3 || command[0]!='"' || command[command.Length-1]!='"')
                throw new IOException();
            string exe=command.Substring(1,command.Length-2);
            string prefix=Path.Combine(root,"Uninstallers")+Path.DirectorySeparatorChar;
            if (!exe.StartsWith(prefix,StringComparison.OrdinalIgnoreCase)) throw new IOException();
            string relative=exe.Substring(prefix.Length);
            if (!System.Text.RegularExpressions.Regex.IsMatch(relative,@"^[A-F0-9]{64}\\Uninstall_Gary\.exe$"))
                throw new IOException();
#if UNINSTALLER
            if (!String.Equals(exe,Assembly.GetExecutingAssembly().Location,StringComparison.OrdinalIgnoreCase))
                throw new IOException();
#endif
        }
    }

    internal static void Register(string root,string exe)
    {
        RequireOrdinary(exe);
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath))
        {
            var existing = key.GetValue("InstallLocation") as string;
            if (existing != null && !String.Equals(existing,root,StringComparison.OrdinalIgnoreCase))
                throw new IOException();
            key.SetValue("DisplayName","Gary");
            key.SetValue("InstallLocation",root);
            key.SetValue("UninstallString","\"" + exe + "\"");
            key.SetValue("NoModify",1);
            key.SetValue("NoRepair",1);
        }
    }

    internal static void Unregister(string root)
    {
        CheckRegistrationOwner(root);
        using (RegistryKey key = Registry.CurrentUser.OpenSubKey(RegistryPath))
        {
            if (key==null) return;
            if (!String.Equals(key.GetValue("InstallLocation") as string,root,StringComparison.OrdinalIgnoreCase))
                throw new IOException();
        }
        Registry.CurrentUser.DeleteSubKey(RegistryPath,false);
    }

    static void RequireOrdinary(string path)
    {
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new IOException();
    }

    static void CheckTree(string directory)
    {
        RequireOrdinary(directory);
        foreach (string entry in Directory.GetFileSystemEntries(directory))
        {
            RequireOrdinary(entry);
            if (Directory.Exists(entry)) CheckTree(entry);
        }
    }

    static int Uninstall(string root, string shortcut)
    {
        string app = Path.Combine(root, "App");
        string ownership = Path.Combine(root, "Gary.installation");
        string gate = Path.Combine(root, "maintenance.active");
        string retired = Path.Combine(root, "Uninstalled-App");
        string executable = Path.Combine(root, @"MaintenanceRuntime\python.exe");
        string shortcutTarget = Path.Combine(root, @"MaintenanceRuntime\pythonw.exe");
        string launcher = Path.Combine(root, "Gary.pyw");
        FileStream maintenanceLock = null;
        string pending = Path.Combine(root,"uninstall.pending");
        try
        {
            RequireOrdinary(root);
            RequireOrdinary(ownership);
            if (File.ReadAllText(ownership) != "Gary.Windows.PerUser.v1\n" ||
                Directory.Exists(Path.Combine(root, "Maintenance"))) throw new IOException();
            CheckRegistrationOwner(root);
            bool ownedShortcut = false;
            if (File.Exists(shortcut))
            {
                RequireOrdinary(shortcut);
                dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
                dynamic link = shell.CreateShortcut(shortcut);
                ownedShortcut = String.Equals((string)link.TargetPath,shortcutTarget,StringComparison.OrdinalIgnoreCase)
                    && (string)link.Arguments == "\"" + launcher + "\" start";
                if (!ownedShortcut) throw new IOException();
            }
            string lockPath = Path.Combine(root,"maintenance.lock");
            if (File.Exists(lockPath)) RequireOrdinary(lockPath);
            maintenanceLock = File.Open(lockPath,FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.ReadWrite);
            maintenanceLock.Lock(0,1);
            bool purge;
            if (File.Exists(pending))
            {
                RequireOrdinary(pending);
                string mode=File.ReadAllText(pending);
                if (mode!="keep-v1" && mode!="purge-v1") throw new IOException();
                purge=mode=="purge-v1";
                if (MessageBox.Show(purge ? "Reprendre la désinstallation avec suppression de Data ?" :
                    "Reprendre la désinstallation en conservant Data ?", "Gary",
                    MessageBoxButtons.OKCancel)!=DialogResult.OK) return 1;
                ClaimUninstallGate(gate);
            }
            else
            {
            if (Directory.Exists(retired)) throw new IOException();
            CheckTree(app);
            CheckTree(Path.Combine(root,"MaintenanceRuntime"));
            RequireOrdinary(launcher);
            var choice = MessageBox.Show("Désinstaller Gary ? Oui conserve les données (choix par défaut). Non propose une suppression complète.",
                                         "Gary",MessageBoxButtons.YesNoCancel,MessageBoxIcon.Question,MessageBoxDefaultButton.Button1);
            if (choice == DialogResult.Cancel) return 1;
            purge = choice == DialogResult.No;
            if (purge && MessageBox.Show("Supprimer définitivement les données locales de cette installation, y compris la base, les caches et le coffre ?",
                    "Gary",MessageBoxButtons.YesNo,MessageBoxIcon.Warning,MessageBoxDefaultButton.Button2)!=DialogResult.Yes) return 1;
            if (purge && Directory.Exists(Path.Combine(root,"Data"))) CheckTree(Path.Combine(root,"Data"));
            ClaimUninstallGate(gate);
            // Only the installed launcher can identify and stop its own server.
            var options = new ProcessStartInfo(executable, "-B -m v5.gary_v5.uninstall_prepare");
            options.WorkingDirectory=app;
            options.CreateNoWindow=true;
            options.UseShellExecute=false;
            try
            {
                using (Process worker = Process.Start(options))
                    if (!worker.WaitForExit(75000) || worker.ExitCode != 0) throw new IOException();
                string intent=Path.Combine(root,"uninstall-intent-"+Guid.NewGuid().ToString("N"));
                using (var stream=File.Open(intent,FileMode.CreateNew))
                {
                    byte[] bytes=System.Text.Encoding.ASCII.GetBytes(purge?"purge-v1":"keep-v1");
                    stream.Write(bytes,0,bytes.Length);
                    stream.Flush(true);
                }
                File.Move(intent,pending);
            }
            catch { if (!File.Exists(pending)) File.Delete(gate); throw; }
            }
            ResumeApplicationRemoval(root);
            if (purge) PurgeData(root);
            string runtime=Path.Combine(root,"MaintenanceRuntime");
            if (Directory.Exists(runtime)) { CheckTree(runtime); Directory.Delete(runtime,true); }
            if (ownedShortcut) File.Delete(shortcut);
            if (File.Exists(launcher)) { RequireOrdinary(launcher); File.Delete(launcher); }
            Unregister(root);
            File.Delete(gate);
            File.Delete(pending);
            File.Delete(ownership);
            MessageBox.Show(purge ? "Gary et ses données actives ont été retirés." :
                "Gary a été désinstallé. Le dossier Data a été conservé.", "Gary");
            return 0;
        }
        catch
        {
            MessageBox.Show("Désinstallation interrompue. Fermez les fichiers utilisés puis relancez le désinstallateur.", "Gary");
            return 3;
        }
        finally
        {
            if (maintenanceLock != null) maintenanceLock.Dispose();
        }
    }

    internal static void PurgeData(string root)
    {
        RequireOrdinary(root);
        string marker=Path.Combine(root,"Gary.installation");
        RequireOrdinary(marker);
        if (File.ReadAllText(marker)!="Gary.Windows.PerUser.v1\n") throw new IOException();
        string data=Path.Combine(root,"Data");
        if (!Directory.Exists(data)) return;
        CheckTree(data);
        Directory.Delete(data,true);
    }

    internal static void RetireApplication(string root)
    {
        RequireOrdinary(root);
        string marker = Path.Combine(root, "Gary.installation");
        RequireOrdinary(marker);
        if (File.ReadAllText(marker) != "Gary.Windows.PerUser.v1\n") throw new IOException();
        string app = Path.Combine(root, "App");
        string retired = Path.Combine(root, "Uninstalled-App");
        CheckTree(app);
        Directory.Move(app,retired);
        CheckTree(retired);
        Directory.Delete(retired,true);
    }

    internal static void ResumeApplicationRemoval(string root)
    {
        RequireOrdinary(root);
        string marker=Path.Combine(root,"Gary.installation");
        string pending=Path.Combine(root,"uninstall.pending");
        RequireOrdinary(marker);
        RequireOrdinary(pending);
        string mode=File.ReadAllText(pending);
        if (File.ReadAllText(marker)!="Gary.Windows.PerUser.v1\n" || (mode!="keep-v1" && mode!="purge-v1"))
            throw new IOException();
        string app=Path.Combine(root,"App"), retired=Path.Combine(root,"Uninstalled-App");
        if (Directory.Exists(app))
        {
            CheckTree(app);
            Directory.Move(app,retired);
        }
        if (Directory.Exists(retired))
        {
            CheckTree(retired);
            Directory.Delete(retired,true);
        }
    }
}
