/**
 * Expo config plugin: LittleNet Parent Device Authentication.
 *
 * Injects a native Android module (ParentDeviceAuth) that wraps the Android
 * system authentication prompt — AndroidX BiometricPrompt with
 * BIOMETRIC_STRONG | DEVICE_CREDENTIAL on API 30+, and a biometric prompt
 * with KeyguardManager device-credential fallback on API 29 and lower.
 *
 * No PIN/pattern/password/biometric data is ever read or stored by the app;
 * authentication stays entirely inside the Android system prompt.
 *
 * The generated native sources are written during `expo prebuild`, so they
 * survive `prebuild --clean`.
 */
const { withAppBuildGradle, withDangerousMod, withMainApplication } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const MODULE_KT = `package com.littlenet.app.deviceauth

import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.facebook.react.bridge.ActivityEventListener
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.module.annotations.ReactModule

/**
 * System-only parent authentication. Never reads, stores, or transmits the
 * user's screen-lock credential or biometric template.
 */
@ReactModule(name = ParentDeviceAuthModule.NAME)
class ParentDeviceAuthModule(private val reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext), ActivityEventListener {

    companion object {
        const val NAME = "ParentDeviceAuth"
        private const val CREDENTIAL_REQUEST_CODE = 31001
    }

    private var pendingPromise: Promise? = null
    private var awaitingDeviceCredential = false

    init {
        reactContext.addActivityEventListener(this)
    }

    override fun getName(): String = NAME

    private fun keyguardManager(): KeyguardManager =
        reactContext.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager

    private fun biometricManager(): BiometricManager = BiometricManager.from(reactContext)

    @ReactMethod
    fun checkParentDeviceAuth(promise: Promise) {
        try {
            val strong = biometricManager()
                .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG)
            val biometricEnrolled = strong == BiometricManager.BIOMETRIC_SUCCESS
            val biometricAvailable = biometricEnrolled ||
                strong == BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED
            val deviceCredentialAvailable = try {
                keyguardManager().isDeviceSecure
            } catch (_: Exception) {
                false
            }
            val result = Arguments.createMap().apply {
                putBoolean("biometricAvailable", biometricAvailable)
                putBoolean("biometricEnrolled", biometricEnrolled)
                putBoolean("deviceCredentialAvailable", deviceCredentialAvailable)
                putBoolean("canAuthenticate", biometricEnrolled || deviceCredentialAvailable)
            }
            promise.resolve(result)
        } catch (e: Exception) {
            promise.reject("CHECK_FAILED", "Unable to query device authentication state: " + e.message, e)
        }
    }

    @ReactMethod
    fun authenticateParentDevice(promise: Promise) {
        val activity = reactContext.currentActivity
        if (activity == null) {
            promise.reject("NO_ACTIVITY", "No foreground activity for the system prompt.")
            return
        }
        if (pendingPromise != null) {
            promise.reject("IN_PROGRESS", "Authentication is already in progress.")
            return
        }
        pendingPromise = promise
        awaitingDeviceCredential = false

        val strongOk = biometricManager()
            .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) ==
            BiometricManager.BIOMETRIC_SUCCESS
        val deviceSecure = try { keyguardManager().isDeviceSecure } catch (_: Exception) { false }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // API 30+: single system prompt accepting strong biometrics or the
            // device credential (PIN / pattern / password).
            showSystemPrompt(
                activity,
                BiometricManager.Authenticators.BIOMETRIC_STRONG or
                    BiometricManager.Authenticators.DEVICE_CREDENTIAL,
                negativeLabel = null,
            )
            return
        }

        // API 29 and lower: the combined authenticator mode is not supported.
        if (strongOk) {
            // Biometric prompt; the negative button falls back to the device
            // credential via KeyguardManager.
            showSystemPrompt(
                activity,
                BiometricManager.Authenticators.BIOMETRIC_STRONG,
                negativeLabel = "Use screen lock",
            )
            return
        }
        if (deviceSecure) {
            launchDeviceCredential(activity)
            return
        }
        settle(null, "NOT_ENROLLED", "No biometric or screen lock is set up on this device.")
    }

    private fun showSystemPrompt(activity: Activity, authenticators: Int, negativeLabel: String?) {
        val fragmentActivity = activity as? FragmentActivity
        if (fragmentActivity == null) {
            settle(null, "NO_ACTIVITY", "The current activity cannot host the system prompt.")
            return
        }
        val executor = ContextCompat.getMainExecutor(reactContext)
        val callback = object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                val method = if (result.authenticationType ==
                    BiometricPrompt.AUTHENTICATION_RESULT_TYPE_DEVICE_CREDENTIAL
                ) "DEVICE_CREDENTIAL" else "BIOMETRIC"
                settle(method, null, null)
            }

            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                if (errorCode == BiometricPrompt.ERROR_USER_CANCELED ||
                    errorCode == BiometricPrompt.ERROR_NEGATIVE_BUTTON
                ) {
                    if (errorCode == BiometricPrompt.ERROR_NEGATIVE_BUTTON &&
                        negativeLabel != null
                    ) {
                        // User chose the screen-lock fallback on API <= 29.
                        launchDeviceCredential(fragmentActivity)
                        return
                    }
                    settle(null, "USER_CANCEL", errString.toString())
                    return
                }
                if (errorCode == BiometricPrompt.ERROR_LOCKOUT ||
                    errorCode == BiometricPrompt.ERROR_LOCKOUT_PERMANENT
                ) {
                    settle(null, "LOCKOUT", errString.toString())
                    return
                }
                settle(null, "FAILED", errString.toString())
            }

            override fun onAuthenticationFailed() {
                // A single failed attempt; the system prompt stays open for
                // retries, so do not settle the promise here.
            }
        }
        val prompt = BiometricPrompt(fragmentActivity, executor, callback)
        val infoBuilder = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Parent Mode")
            .setSubtitle("Confirm it is you to continue")
            .setAllowedAuthenticators(authenticators)
        if (negativeLabel != null) {
            infoBuilder.setNegativeButtonText(negativeLabel)
        }
        try {
            prompt.authenticate(infoBuilder.build())
        } catch (e: Exception) {
            settle(null, "FAILED", "Could not show the system prompt: " + e.message)
        }
    }

    private fun launchDeviceCredential(activity: Activity) {
        awaitingDeviceCredential = true
        val intent: Intent? = try {
            keyguardManager().createConfirmDeviceCredentialIntent(
                "Parent Mode",
                "Confirm your screen lock to continue",
            )
        } catch (_: Exception) {
            null
        }
        if (intent == null) {
            awaitingDeviceCredential = false
            settle(null, "NOT_ENROLLED", "No screen lock is set up on this device.")
            return
        }
        try {
            activity.startActivityForResult(intent, CREDENTIAL_REQUEST_CODE)
        } catch (e: Exception) {
            awaitingDeviceCredential = false
            settle(null, "FAILED", "Could not open the screen-lock prompt: " + e.message)
        }
    }

    private fun settle(method: String?, errorCode: String?, message: String?) {
        val promise = pendingPromise
        pendingPromise = null
        awaitingDeviceCredential = false
        if (promise == null) return
        if (method != null) {
            val result = Arguments.createMap().apply {
                putBoolean("success", true)
                putString("method", method)
            }
            promise.resolve(result)
        } else {
            val result = Arguments.createMap().apply {
                putBoolean("success", false)
                putString("error", errorCode ?: "FAILED")
                if (message != null) putString("message", message)
            }
            promise.resolve(result)
        }
    }

    override fun onActivityResult(
        activity: Activity,
        requestCode: Int,
        resultCode: Int,
        data: Intent?,
    ) {
        if (requestCode != CREDENTIAL_REQUEST_CODE || !awaitingDeviceCredential) return
        if (resultCode == Activity.RESULT_OK) {
            settle("DEVICE_CREDENTIAL", null, null)
        } else {
            settle(null, "USER_CANCEL", "Screen-lock confirmation was cancelled.")
        }
    }

    override fun onNewIntent(intent: Intent) = Unit
}
`;

const PACKAGE_KT = `package com.littlenet.app.deviceauth

import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.uimanager.ViewManager

class ParentDeviceAuthPackage : ReactPackage {
    override fun createNativeModules(reactContext: ReactApplicationContext): List<NativeModule> =
        listOf(ParentDeviceAuthModule(reactContext))

    override fun createViewManagers(reactContext: ReactApplicationContext): List<ViewManager<*, *>> =
        emptyList()
}
`;

function withParentDeviceAuthNativeFiles(config) {
  return withDangerousMod(config, [
    'android',
    async (config) => {
      const projectRoot = config.modRequest.projectRoot;
      const dir = path.join(
        projectRoot, 'android', 'app', 'src', 'main', 'java',
        'com', 'littlenet', 'app', 'deviceauth',
      );
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, 'ParentDeviceAuthModule.kt'), MODULE_KT);
      fs.writeFileSync(path.join(dir, 'ParentDeviceAuthPackage.kt'), PACKAGE_KT);
      return config;
    },
  ]);
}

function withParentDeviceAuthGradleDep(config) {
  return withAppBuildGradle(config, (config) => {
    const dep = 'implementation("androidx.biometric:biometric:1.2.0-alpha05")';
    if (!config.modResults.contents.includes('androidx.biometric:biometric')) {
      config.modResults.contents = config.modResults.contents.replace(
        /dependencies\s*\{/,
        `dependencies {\n    ${dep}`,
      );
    }
    return config;
  });
}

function withParentDeviceAuthPackage(config) {
  return withMainApplication(config, (config) => {
    const src = config.modResults.contents;
    if (src.includes('ParentDeviceAuthPackage')) return config;
    let out = src;
    if (!out.includes('import com.littlenet.app.deviceauth.ParentDeviceAuthPackage')) {
      out = out.replace(
        /import ([^\n]*MainApplication[^\n]*\n|package [^\n]*\n)/,
        (m) => m + 'import com.littlenet.app.deviceauth.ParentDeviceAuthPackage\n',
      );
      if (!out.includes('import com.littlenet.app.deviceauth.ParentDeviceAuthPackage')) {
        const lines = out.split('\n');
        const pkgIdx = lines.findIndex((l) => l.startsWith('package '));
        lines.splice(pkgIdx + 1, 0, 'import com.littlenet.app.deviceauth.ParentDeviceAuthPackage');
        out = lines.join('\n');
      }
    }
    // Register in getPackages(): `packages.add(ParentDeviceAuthPackage())`
    // Handles both `PackageList(this).packages` and `packages.add(...)` styles.
    if (/packages\.add\(/.test(out)) {
      out = out.replace(
        /(packages\.add\([^\n]*\n)/,
        '$1        packages.add(ParentDeviceAuthPackage())\n',
      );
    } else if (/PackageList\(this\)\.packages\.apply\s*\{/.test(out)) {
      // Expo template style: PackageList(this).packages.apply { ... }
      out = out.replace(
        /PackageList\(this\)\.packages\.apply\s*\{/,
        'PackageList(this).packages.apply {\n          add(ParentDeviceAuthPackage())',
      );
    } else if (/PackageList\(this\)\.packages/.test(out)) {
      out = out.replace(
        /return PackageList\(this\)\.packages/,
        'return PackageList(this).packages.apply { add(ParentDeviceAuthPackage()) }',
      );
    } else if (/override fun getPackages\(\): List<ReactPackage>/.test(out)) {
      out = out.replace(
        /(override fun getPackages\(\): List<ReactPackage>[^\n]*\n)/,
        '$1        // ParentDeviceAuth registered below\n',
      );
    }
    config.modResults.contents = out;
    return config;
  });
}

function withParentDeviceAuth(config) {
  config = withParentDeviceAuthNativeFiles(config);
  config = withParentDeviceAuthGradleDep(config);
  config = withParentDeviceAuthPackage(config);
  return config;
}

module.exports = withParentDeviceAuth;
