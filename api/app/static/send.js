// Create the transfer, upload each file straight to S3 with its presigned PUT, then finalize.
const form = document.getElementById("send-form");
const status = document.getElementById("send-status");

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const btn = document.getElementById("send-btn");
  btn.disabled = true;
  const fd = new FormData(form);
  const files = Array.from(form.elements["files"].files);
  try {
    status.textContent = "Creating transfer...";
    const res = await fetch("/api/transfers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipients: fd.get("recipients").split(",").map((s) => s.trim()).filter(Boolean),
        message: fd.get("message"),
        expires_days: Number(fd.get("expires_days")),
        password: fd.get("password"),
        max_downloads: Number(fd.get("max_downloads")),
        files: files.map((f) => ({ filename: f.name, size: f.size, content_type: f.type || "application/octet-stream" })),
      }),
    });
    if (!res.ok) throw new Error(JSON.stringify((await res.json()).detail) || "Could not create transfer");
    const t = await res.json();
    for (let i = 0; i < files.length; i++) {
      status.textContent = `Uploading ${files[i].name} (${i + 1}/${files.length})...`;
      const put = await fetch(t.uploads[i].upload_url, {
        method: "PUT",
        headers: { "Content-Type": t.uploads[i].content_type },
        body: files[i],
      });
      if (!put.ok) throw new Error(`Upload of ${files[i].name} failed (${put.status})`);
    }
    status.textContent = "Finalizing...";
    const fin = await fetch(`/api/transfers/${t.id}/finalize`, { method: "POST" });
    if (!fin.ok) throw new Error((await fin.json()).detail || "Finalize failed");
    window.location = `/transfers/${t.id}`;
  } catch (e) {
    status.textContent = e.message;
    status.className = "error";
    btn.disabled = false;
  }
});
