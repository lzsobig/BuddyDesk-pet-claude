# WinIsland Thoughts & FAQ

> Ahem, here are a few personal thoughts.

## A few thoughts

1. **The app becoming unresponsive**: This was fixed in [PR #196](https://github.com/WinIslandProject/WinIsland/pull/196), so you can use the nightly build.

2. **The developers' attitude**: I cannot personally speak for foocean. Chi Putao seems fine to me. As for claims that we are ruining the community atmosphere, I do not think I have done anything of the sort. Why attribute one person's possible problem to the whole team?

3. **Antivirus false positives**: Chi Putao has already replied, so I am sharing that response here:

   > **Another developer:**
   >
   > The detections we have seen from Windows' built-in antivirus are not caused by our own code, but by Rust libraries and characteristics of Rust programs. Rust programs commonly statically link substantial runtime support and dependencies into the executable. Legitimate and malicious software can both contain this shared code, and some antivirus detection methods match that code, causing false positives. Many Rust programs have encountered this.
   >
   > If you are still unsure, see:
   >
   > - [rust-clippy#12622](https://github.com/rust-lang/rust-clippy/issues/12622)
   > - [rust#88297](https://github.com/rust-lang/rust/issues/88297): Even a Hello World program can trigger a detection, so it is not surprising for a larger application such as WinIsland to encounter one. Although the issue is five years old, that does not mean similar problems have all been fixed.
   >
   > Even Microsoft's official Windows API repository has encountered false positives: [microsoft/windows-rs#3993](https://github.com/microsoft/windows-rs/issues/3993). Its code is unlikely to be malicious either. If Microsoft's own software can be flagged by Windows antivirus, software made by others can encounter the same problem.
   >
   > If you remain unconvinced, I recommend reviewing the source. Our code is open source, and release binaries are built from that source and uploaded by GitHub Actions. You are welcome to inspect it. If you do find malicious code, please report it.

4. **Claims that the software is not very good**: There is not much I can say to that. You can use another application, though you may end up with one built on a WebView. WebViews make UI development convenient, but that convenience can come with performance costs. WinIsland uses a native approach with Windows APIs and Skia on D3D. D3D has plenty of unusual bugs, so this combination is uncommon in AI-generated projects unless someone has a specific design in mind and asks AI to implement it.

5. **Criticism of us**: I do not personally mind it, though I cannot speak for everyone else. Bug reports and suggestions are welcome. Please follow the pull request guidelines and issue templates.

6. **Restrictions on what people can say**: Do we have any? I am not aware of them.

7. **Claims of careless work**: You can ask an AI reviewer or a Rust backend developer to review the project. I do not think they would call it careless work. That does not mean it is perfect, but I would prefer criticism with reasons rather than unsupported claims, especially when there is so much AI slop on GitHub that goes unmentioned.

8. **Font issues**: We will work on them. I raised this with Chi Putao in early versions, but finding a suitable font with a small file size has been difficult.

That should be everything for now.

---

## WinIsland FAQ

### Q: Does this application have a backdoor?

**A:** The source is on GitHub, and you are welcome to review it. If you are worried about a backdoor, you do not have to use the application; we are not trying to win over people who only want to pick a fight.

### Q: Why is WinIsland not picking up audio?

**A:** Check that the corresponding application is enabled in your settings.

### Q: Why is NetEase Cloud Music not detected?

**A:** Enable SMTC in NetEase Cloud Music's settings. For lyrics and progress bar support, install [BetterNCM](https://github.com/std-microblock/BetterNCM-Installer).

### Q: Why does the application not open?

**A:** Check whether your graphics card supports DirectX 12.

### Q: Are other music players supported?

**A:** Compatibility is not guaranteed; it depends on the player's SMTC support.

### Q: Why are automatic updates not working?

**A:** If access to GitHub is slow or unavailable, use a VPN or another service that improves access to GitHub.

### Q: Why won't the application open, or why does it report that VCRUNTIME140.dll is missing?

**A:** If `VCRUNTIME140.dll` is missing, install both the x64 and x86 versions of the Visual C++ 2015–2022 Redistributable:

- x64: [Download Visual C++ Redistributable x64](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- x86: [Download Visual C++ Redistributable x86](https://aka.ms/vs/17/release/vc_redist.x86.exe)
