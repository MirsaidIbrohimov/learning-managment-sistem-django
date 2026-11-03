plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Imzo kaliti repodan tashqarida. Parol faqat muhit o'zgaruvchisidan olinadi.
val keystorePath = System.getenv("ITC_KEYSTORE") ?: "${System.getProperty("user.home")}/.itc-academy-signing/itc-academy-release.jks"
val keystorePassword: String? = System.getenv("ITC_KEYSTORE_PASSWORD")

android {
    namespace = "uz.itcacademy.lms"
    compileSdk = 35

    defaultConfig {
        // Paket va imzo TWA bilan bir xil: o'rnatilgan ilova shu versiyaga yangilanadi
        applicationId = "uz.itcacademy.lms"
        minSdk = 24
        targetSdk = 35
        versionCode = 3
        versionName = "2.1.0"
        buildConfigField("String", "SITE", "\"https://itc-academy.uz\"")
    }

    signingConfigs {
        if (keystorePassword != null) {
            create("release") {
                storeFile = file(keystorePath)
                storePassword = keystorePassword
                keyAlias = "itcacademy"
                keyPassword = keystorePassword
            }
        }
    }

    buildTypes {
        debug {
            // Faqat sinov: lokal server. Release doim itc-academy.uz
            val site = providers.gradleProperty("itcSite").orNull
            if (site != null) buildConfigField("String", "SITE", "\"$site\"")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (keystorePassword != null) signingConfig = signingConfigs.getByName("release")
        }
        // Faqat sinov: release bilan bir xil siqilgan kod, lokal server bilan. Debug'da R8 ishlamaydi.
        providers.gradleProperty("itcQa").orNull?.let { site ->
            create("qa") {
                initWith(getByName("release"))
                matchingFallbacks += "release"
                signingConfig = signingConfigs.getByName("debug")
                buildConfigField("String", "SITE", "\"$site\"")
            }
        }
    }
    if (providers.gradleProperty("itcQa").isPresent) {
        sourceSets["qa"].manifest.srcFile("src/debug/AndroidManifest.xml")
        sourceSets["qa"].res.srcDir("src/debug/res")
    }

    // Tarjimalar Windows ilovasi bilan bitta manbadan: i18n/app.json + saytning lug'ati
    sourceSets["main"].assets.srcDir("../../../windows/ui/i18n")

    buildFeatures { compose = true; buildConfig = true }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}

dependencies {
    val bom = platform("androidx.compose:compose-bom:2025.04.01")
    implementation(bom)
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("dev.chrisbanes.haze:haze:1.5.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.1")
    testImplementation("junit:junit:4.13.2")
}
