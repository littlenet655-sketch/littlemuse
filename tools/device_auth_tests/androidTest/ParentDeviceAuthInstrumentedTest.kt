package com.littlenet.app.deviceauth

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.WritableMap
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Instrumented tests for [ParentDeviceAuthModule].
 *
 * Run on an emulator (API 30+ recommended):
 *   ./gradlew :app:connectedDebugAndroidTest \
 *     -Pandroid.testInstrumentationRunnerArguments.class=com.littlenet.app.deviceauth.ParentDeviceAuthInstrumentedTest
 *
 * DROP-IN: copy this file to
 *   mobile_app/android/app/src/androidTest/java/com/littlenet/app/deviceauth/ParentDeviceAuthInstrumentedTest.kt
 * after `npx expo prebuild --platform android --clean`, and ensure
 * app/build.gradle declares:
 *   defaultConfig { testInstrumentationRunner "androidx.test.runner.AndroidJUnitRunner" }
 *   dependencies {
 *     androidTestImplementation "androidx.test.ext:junit:1.2.1"
 *     androidTestImplementation "androidx.test:runner:1.6.2"
 *   }
 *
 * These tests assert the module's contract WITHOUT ever touching a real
 * credential: they only verify the shape and safety properties of the
 * checkParentDeviceAuth result map.
 */
@RunWith(AndroidJUnit4::class)
class ParentDeviceAuthInstrumentedTest {

    private fun module(): ParentDeviceAuthModule {
        val appContext = InstrumentationRegistry.getInstrumentation().targetContext
        val reactContext = ReactApplicationContext(appContext)
        return ParentDeviceAuthModule(reactContext)
    }

    private class CapturingPromise : Promise {
        val latch = CountDownLatch(1)
        var resolved: Any? = null
        var rejectedCode: String? = null
        override fun resolve(value: Any?) { resolved = value; latch.countDown() }
        override fun reject(code: String, message: String?) { rejectedCode = code; latch.countDown() }
        override fun reject(code: String, throwable: Throwable?) { rejectedCode = code; latch.countDown() }
        override fun reject(code: String, message: String?, throwable: Throwable?) { rejectedCode = code; latch.countDown() }
        override fun reject(throwable: Throwable) { rejectedCode = "EX"; latch.countDown() }
        override fun reject(throwable: Throwable, userInfo: WritableMap?) { rejectedCode = "EX"; latch.countDown() }
        override fun reject(code: String, userInfo: WritableMap) { rejectedCode = code; latch.countDown() }
        override fun reject(code: String, throwable: Throwable?, userInfo: WritableMap?) { rejectedCode = code; latch.countDown() }
        fun awaitResolve(): Any? {
            assertTrue("promise never settled", latch.await(10, TimeUnit.SECONDS))
            assertNull("promise rejected with $rejectedCode", rejectedCode)
            return resolved
        }
    }

    @Test
    fun moduleName_isParentDeviceAuth() {
        assertEquals("ParentDeviceAuth", module().name)
    }

    @Test
    fun check_returnsExpectedKeys_withBooleanValues() {
        val promise = CapturingPromise()
        module().checkParentDeviceAuth(promise)
        val map = promise.awaitResolve() as com.facebook.react.bridge.ReadableMap
        for (key in listOf(
            "biometricAvailable",
            "biometricEnrolled",
            "deviceCredentialAvailable",
            "canAuthenticate"
        )) {
            assertTrue("missing key: $key", map.hasKey(key))
            // getBoolean throws if the value is not a boolean — that is the assertion.
            map.getBoolean(key)
        }
    }

    @Test
    fun check_canAuthenticate_isConsistentWithComponents() {
        val promise = CapturingPromise()
        module().checkParentDeviceAuth(promise)
        val map = promise.awaitResolve() as com.facebook.react.bridge.ReadableMap
        val expected = map.getBoolean("biometricEnrolled") ||
            map.getBoolean("deviceCredentialAvailable")
        assertEquals(
            "canAuthenticate must equal (biometricEnrolled || deviceCredentialAvailable)",
            expected,
            map.getBoolean("canAuthenticate")
        )
    }

    @Test
    fun check_neverExposesCredentialMaterial() {
        val promise = CapturingPromise()
        module().checkParentDeviceAuth(promise)
        val map = promise.awaitResolve() as com.facebook.react.bridge.ReadableMap
        val keys = map.keySet().map { it.lowercase() }
        val forbidden = listOf("pin", "password", "pattern", "template", "secret", "token", "credential")
        for (bad in forbidden) {
            assertTrue(
                "result map must never expose '$bad'",
                keys.none { it.contains(bad) }
            )
        }
        // Exactly the four documented keys — nothing extra leaks out.
        assertEquals(4, keys.size)
    }

    @Test
    fun check_isRepeatable_andDoesNotThrow() {
        val m = module()
        repeat(3) {
            val promise = CapturingPromise()
            m.checkParentDeviceAuth(promise)
            promise.awaitResolve()
        }
    }

    @Test
    fun authenticate_withoutActivity_rejectsCleanly() {
        // On a bare instrumentation context there is no foreground activity;
        // the module must reject with NO_ACTIVITY rather than crash.
        val promise = CapturingPromise()
        module().authenticateParentDevice(promise)
        assertTrue(promise.latch.await(10, TimeUnit.SECONDS))
        // Either NO_ACTIVITY (no foreground activity) or a settled result —
        // the key assertion is that the call never throws.
        assertTrue(
            promise.rejectedCode == "NO_ACTIVITY" || promise.resolved != null
        )
    }
}
