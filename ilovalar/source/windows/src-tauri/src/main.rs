// ITC Academy — Windows desktop ilovasi.
// Arxitektura: bitta WebView2 oyna https://itc-academy.uz ni to'g'ridan-to'g'ri ochadi.
// XAVFSIZLIK:
//  * Masofaviy sahifaga hech qanday Tauri IPC / native buyruq ochilmagan
//    (capabilities'da `remote` yo'q, invoke handler yo'q).
//  * TLS tekshiruvi WebView2 standartida — o'chirilmagan.
//  * Ilova ichida faqat LMS domeni va to'lov provayderlari ochiladi
//    (to'lovdan qaytishda sessiya cookie saqlanishi uchun); boshqa havolalar
//    tizim brauzerida ochiladi.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::atomic::{AtomicUsize, Ordering};

use tauri::webview::{NewWindowFeatures, NewWindowResponse};
use tauri::{AppHandle, Manager, Runtime, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use url::Url;

const START_URL: &str = "https://itc-academy.uz/";

/// Ilova oynasida ochilishiga ruxsat etilgan domenlar (o'zi va subdomenlari).
const IN_APP_HOSTS: &[&str] = &["itc-academy.uz", "itcreative.uz", "tezcheck.uz", "checkout.uz"];
/// Tizimga topshiriladigan (tashqi) sxemalar.
const EXTERNAL_SCHEMES: &[&str] = &["https", "http", "mailto", "tel", "tg"];

fn host_allowed(host: &str) -> bool {
    IN_APP_HOSTS
        .iter()
        .any(|d| host == *d || host.ends_with(&format!(".{d}")))
}

fn in_app(url: &Url) -> bool {
    match url.scheme() {
        "https" => url.host_str().map(host_allowed).unwrap_or(false),
        // WebView2 ichki sahifalari (masalan, about:blank)
        "about" | "data" | "blob" => true,
        _ => false,
    }
}

fn open_external(url: &Url) {
    if EXTERNAL_SCHEMES.contains(&url.scheme()) {
        let _ = tauri_plugin_opener::open_url(url.as_str(), None::<&str>);
    }
}

static WINDOW_SEQ: AtomicUsize = AtomicUsize::new(1);

/// LMS oynasi. `target=_blank` / `window.open` bilan ochilgan ichki sahifalar ham
/// xuddi shu qoidalarga ega yangi oynada ochiladi (masalan, sertifikat yoki PDF).
fn lms_window<R: Runtime>(
    app: &AppHandle<R>,
    label: &str,
    url: Url,
    features: Option<NewWindowFeatures>,
) -> tauri::Result<WebviewWindow<R>> {
    let handle = app.clone();
    let mut builder = WebviewWindowBuilder::new(app, label, WebviewUrl::External(url))
        .title("ITC Academy")
        .inner_size(1280.0, 820.0)
        .min_inner_size(400.0, 600.0)
        .zoom_hotkeys_enabled(true)
        .on_document_title_changed(|window, title| {
            let title = title.trim();
            let _ = window.set_title(if title.is_empty() { "ITC Academy" } else { title });
        })
        .on_navigation(|url| {
            if in_app(url) {
                true
            } else {
                open_external(url);
                false
            }
        })
        .on_new_window(move |url, features| {
            if !in_app(&url) {
                open_external(&url);
                return NewWindowResponse::Deny;
            }
            let label = format!("w{}", WINDOW_SEQ.fetch_add(1, Ordering::Relaxed));
            let blank = Url::parse("about:blank").expect("about:blank");
            match lms_window(&handle, &label, blank, Some(features)) {
                Ok(window) => NewWindowResponse::Create { window },
                Err(_) => NewWindowResponse::Deny,
            }
        });
    builder = match features {
        Some(features) => builder.window_features(features),
        None => builder.center(),
    };
    builder.build()
}

fn main() {
    tauri::Builder::default()
        // Ikkinchi marta ishga tushirilsa — mavjud oyna oldinga chiqariladi
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let start = Url::parse(START_URL).expect("START_URL");
            lms_window(app.handle(), "main", start, None)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("ITC Academy ishga tushmadi");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn u(s: &str) -> Url {
        Url::parse(s).unwrap()
    }

    #[test]
    fn lms_and_payment_stay_in_app() {
        assert!(in_app(&u("https://itc-academy.uz/dashboard/")));
        assert!(in_app(&u("https://www.itc-academy.uz/")));
        assert!(in_app(&u("https://pay.tezcheck.uz/checkout?id=1")));
        assert!(in_app(&u("https://checkout.uz/x")));
    }

    #[test]
    fn other_sites_and_plain_http_leave_app() {
        assert!(!in_app(&u("http://itc-academy.uz/")));
        assert!(!in_app(&u("https://itc-academy.uz.evil.com/")));
        assert!(!in_app(&u("https://evilitc-academy.uz/")));
        assert!(!in_app(&u("https://youtube.com/watch?v=1")));
        assert!(!in_app(&u("file:///C:/Windows/win.ini")));
    }
}
