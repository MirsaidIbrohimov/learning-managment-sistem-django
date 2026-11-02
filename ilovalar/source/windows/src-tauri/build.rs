fn main() {
    // Ilova buyruqlari faqat capabilities'da aniq ruxsat berilgan oynalarga ochiladi.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "has_session",
            "login",
            "auth_start",
            "auth_poll",
            "auth_cancel",
            "logout",
            "api",
            "open_web",
            "open_external",
        ]),
    ))
    .expect("tauri build");
}
