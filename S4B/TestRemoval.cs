using System;
using System.IO;

static class TestRemoval
{
    static int Main(string[] args)
    {
        string root=Path.GetFullPath(args[0]);
        if (Directory.Exists(root)) return 2;
        string data=Path.Combine(root,"Data");
        Directory.CreateDirectory(data);
        Directory.CreateDirectory(Path.Combine(root,"App"));
        File.WriteAllText(Path.Combine(data,"fictitious.dpapi"),"fixture");
        string marker=Path.Combine(root,"Gary.installation");
        File.WriteAllText(marker,"foreign");
        try { Installer.PurgeData(root); return 3; } catch(IOException) {}
        File.WriteAllText(marker,"Gary.Windows.PerUser.v1\n");
        string legacy=Path.Combine(root,"Uninstall_Gary.exe");
        File.WriteAllText(legacy,"foreign residual");
        string first=Installer.PlaceUninstaller(root,new MemoryStream(new byte[]{1}));
        if (first!=Installer.PlaceUninstaller(root,new MemoryStream(new byte[]{1}))) return 6;
        string second=Installer.PlaceUninstaller(root,new MemoryStream(new byte[]{2}));
        if (first==second || File.ReadAllText(legacy)!="foreign residual") return 7;
        File.WriteAllBytes(second,new byte[]{9});
        try { Installer.PlaceUninstaller(root,new MemoryStream(new byte[]{2})); return 8; } catch(IOException) {}
        string app=Path.Combine(root,"App");
        string locked=Path.Combine(app,"locked.txt");
        File.WriteAllText(locked,"locked");
        File.WriteAllText(Path.Combine(root,"uninstall.pending"),"keep-v1");
        using (File.Open(locked,FileMode.Open,FileAccess.Read,FileShare.None))
        {
            try { Installer.ResumeApplicationRemoval(root); return 9; }
            catch(IOException) {}
        }
        // Model an interruption after App was renamed and some files were removed.
        string retired=Path.Combine(root,"Uninstalled-App");
        if (Directory.Exists(app)) Directory.Move(app,retired);
        Installer.ResumeApplicationRemoval(root);
        Installer.ResumeApplicationRemoval(root);
        if(!File.Exists(Path.Combine(data,"fictitious.dpapi"))) return 4;
        Installer.PurgeData(root);
        if(Directory.Exists(data) || !File.Exists(marker)) return 5;
        Console.WriteLine("Windows filesystem: ownership, two uninstaller versions, locked App and resumable removal OK.");
        return 0;
    }
}
