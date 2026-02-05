# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class fm.tunetrivia.mobile.**$$serializer { *; }
-keepclassmembers class fm.tunetrivia.mobile.** {
    *** Companion;
}
-keepclasseswithmembers class fm.tunetrivia.mobile.** {
    kotlinx.serialization.KSerializer serializer(...);
}
