# Minecraft Fabric mod (Java + Gradle)

A Fabric mod is a Java/Gradle project, NOT Python. **First check the toolchain exists:**
`java -version` (need JDK 17+ for modern MC) and note Fabric uses the **Gradle wrapper
(`./gradlew`)** which downloads Gradle itself — you do NOT need Gradle installed, only a JDK.
If there's no JDK, say so — you cannot build it. Don't waste steps fetching the example
repo over and over; scaffold the known structure below.

## Minimal project layout
```
mymod/
  build.gradle                 # deps: fabric-loom plugin, minecraft, fabric-api, yarn mappings
  gradle.properties            # versions: minecraft_version, loader_version, fabric_version
  settings.gradle              # pluginManagement for fabric-loom
  gradle/wrapper/…             # the wrapper (gradlew + jar)
  src/main/java/com/example/mymod/ExampleMod.java
  src/main/resources/fabric.mod.json          # mod metadata + entrypoints
  src/main/resources/mymod.mixins.json        # (if using mixins)
```

## fabric.mod.json (the mod manifest)
```json
{
  "schemaVersion": 1,
  "id": "mymod",
  "version": "1.0.0",
  "name": "My Mod",
  "environment": "*",
  "entrypoints": { "main": ["com.example.mymod.ExampleMod"] },
  "depends": { "fabricloader": ">=0.15.0", "minecraft": "~1.20.4" }
}
```

## Entry point + registering an item
```java
package com.example.mymod;
import net.fabricmc.api.ModInitializer;
import net.minecraft.item.Item;
import net.minecraft.registry.Registry;
import net.minecraft.registry.Registries;
import net.minecraft.util.Identifier;

public class ExampleMod implements ModInitializer {
    public static final Item CUSTOM_ITEM = new Item(new Item.Settings());
    @Override public void onInitialize() {
        Registry.register(Registries.ITEM, new Identifier("mymod", "custom_item"), CUSTOM_ITEM);
    }
}
```
Also add a lang file (`assets/mymod/lang/en_us.json`) and a model/texture for the item.

## Build + verify
`./gradlew build` (Linux/mac) or `gradlew.bat build` (Windows) → jar in `build/libs/`.
The build downloads Minecraft + mappings on first run (slow). If no JDK is installed, the
build cannot run — report that honestly rather than claiming success. See
[[Writing a build that passes review]].
