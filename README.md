# BUILD Map Importer - Blender Add-on
This Blender Add-on allows you to import maps in the BUILD format as used by games such as Blood or Duke Nukem 3D.  
It’s a great way to explore countless community-made usermaps or breathe new life into your own creations.  

Find it on the Blender Extensions Platform: [BUILD Map Importer](https://extensions.blender.org/add-ons/io-import-build-map/)

You can find an example map and textures in the file **example-map-and-textures.zip** in the [latest Release](https://github.com/jensnt/io_import_build_map/releases/latest)

Starting with version 1.4.0 you can now simply set your **games installation folder** as your Texture folder!  
Textures will be automatically extracted from .ART, .GRP and .RFF files. (.png/.jpg files still work)

![E1L1](/images/e1l1.png)


## Installation from Blender Extensions Platform
Starting with Blender 4.2 and newer you can install the Add-on directly from within Blender:
- In Blender go to Edit -> Preferences -> Get Extensions
- Allow Online Access if not done already.
- Search for "BUILD Map Importer" and press "Install".

Or:

You can find the Add-on on the Blender Extensions Platform: [BUILD Map Importer](https://extensions.blender.org/add-ons/io-import-build-map/)

Use the "Get Add-on" Button to install it. 

## Installation from GitHub
To install the Add-on from GitHub you need [Blender](https://www.blender.org/) in version 2.93 or later.

1. Download the [latest Version](https://github.com/jensnt/io_import_build_map/releases/latest) from the Release Page. You need the file **io_import_build_map.zip**. 
3. Install the Add-on by opening the Blender Preferences and clicking on `Install…` button at the top of the "Add-ons" section.  
Then browse for the zip file you downloaded and click `Install Add-on`.
5. The Add-on will not be enabled automatically. You have to enable it by checking it's check box in the Add-ons list before you can use it.

## Setting Texture Folder Paths
![Preferences](/images/preferences.png)

The Add-on has it's own preferences where you can set paths to your texture folders.  
Starting with version 1.4.0 you can now directly set your **games installation folders** here!  
Textures will be automatically extracted from .ART, .GRP and .RFF files.  

The old way of extracting textures from games manually is still supported. See: [Extracting textures](https://github.com/jensnt/io_import_build_map#extracting-textures)

You can also use the texture folder from the file **example-map-and-textures.zip** you can find in the [latest Version](https://github.com/jensnt/io_import_build_map/releases/latest).  
It contains a small set of free textures for the example map **SHOCK.MAP**.  

#### If you are providing PNG or JPG files as textures, they need to use one of the following numbering formats as name:
- As created by the Xtract tool: 056-002.png
- BUILD tile number as name: 0568.png or tile0568.png (up to 8 leading zeros allowed)

## Import Options

![Import Options](/images/import-options.png)

The following Import Options are available:

- **Object Prefix**
  - This option specifies a prefix that will be used in the name of every imported object.
- **Split Sectors**
  - If enabled, the floor and ceiling of every sector will be split off into separate objects.  
    This is necessary to import custom properties from BUILD-Map structures for sectors.
- **Split Walls**
  - If enabled, walls will be split off into separate objects.  
    This is necessary to import custom properties from BUILD-Map structures for walls.
- **Split Sky**
  - If enabled, floors and ceilings with parallaxing enabled and associated walls will be split off into separate objects and sorted into the "Sky" collection.
- **Scale Sprites as in Game**
  - Some special sprites (e.g. weapons and ammo) can have a different scale in game compared to map editors.  
    If this option is enabled, the importer will try to scale them as they appear in game.
- **Wall Sprite Offset**
  - Separate wall sprites from walls as specified by this offset.  
    This is useful to avoid Z-fighting.  
    A small offset like 0.01 m is enough in many cases.
- **Use Priority/Mod Folder**
  - If a Priority/Mod texture folder is specified in the Add-on preferences,  
    you can use this option to enable or disable the usage of Priority/Mod textures.  
    These textures will take priority over the normal Texture folder.
- **Prioritize .png/.jpg files**
  - If enabled, the Add-on will first search for .png and .jpg files, prioritizing them over native game .art files.
    This is not encouraged because native game .art files offer additional meta information used e.g. for correct sprite offsets.
- **Reuse Materials**
  - If enabled, materials that already exist in the blend file, having the same name as this Add-on would create, will be reused instead of creating new ones.  
    If disabled, new materials will be created with a suffix.
- **Shade to Vertex Colors**
  - Save Ceiling, Floor, Wall and Sprite Shade values as Vertex Color Attributes and use those in created Materials.
- **Pixel Shading**
  - If enabled, textures will render with hard pixel edges instead of interpolation.
- **Procedural Material Effects**
  - If enabled, additional shader nodes will be created in materials to add procedural details.  
    This works best with "Pixel Shading" disabled.
- **Use Back Face Culling**
  - If enabled, use back-face culling in created materials to hide the back side of faces.
- **Heuristic Wall Search**
  - Try to find neighboring walls between sectors based on their position.  
    This might fix errors in the map but can also introduce errors.
- **Ignore Map Errors**
  - If you encounter a corrupted map that gives you errors where for example the number of walls appears incorrect, you can try this option.  
    The importer will try to skip corrupted parts of the map.  
    No guarantee for success, though.

## Custom Properties

One feature of this Add-on is that it can save the original map data for every sector, wall and sprite into custom properties of those objects.  
For Sectors and Walls you need to enable the Import options **Split Sectors** and **Split Walls** for this to work.  
This allows for debugging maps or for reusing those properties in Blender.

![Custom Properties](/images/custom-props.png)

## Extracting textures
You can use the textures from the file **example-map-and-textures.zip** you can find in the [latest Version](https://github.com/jensnt/io_import_build_map/releases/latest).  
Another small free set of compatible textures is available in this project:  
https://github.com/LukeKenTeam/LukeKen3D

**If you want to use textures from the original game, you must own a legitimate copy of the game.
Textures extracted from the game are copyrighted material and may not be redistributed or shared.**

You can get textures from your original game as follows:

- You will need the .GRP file from your game.
- You can extract the textures from the .GRP file using the Xtract tool.
- For Windows, you can get it from either of these sites:
  - [The ReBUILD Project](https://blood.sourceforge.net/rebuild.php)
  - [RTCM - Files - Source Code BUILD Windows Tools and Engines](http://www.dukertcm.com/knowledge-base/downloads-rtcm/src-build-mod-win/) (HTTP only!) (look for: "ReBUILD Windows xtract")
- For macOS, you can use a port of Xtract by rusq:
  - [Xtract macOS port](https://github.com/rusq/xtract)
- Place the .GRP file and the Xtract tool in the same folder, open a command line in that folder and execute the following:
```
.\Xtract.exe YOURGAME.GRP
```
- It will give you the textures as .tga files which you need to convert to png.
- To convert the files to png, you can use XnConvert: [XnConvert · Batch Image Converter](https://www.xnview.com/en/xnconvert/#downloads)
  - In the "Input"-Tab: Add folder "tiles" that was generated by Xtract
  - In the "Actions"-Tab: Add action "Transparent color" (#fc00fc (Red:252; Green:0; Blue:252))
  - In the "Output"-Tab select the output folder
  - Set Format to "PNG - Portable Network Graphics"
  - Set Filename to just "{Filename}" without "_result"
- Alternatively you can do the same using [ImageMagick](https://imagemagick.org/) by executing the following in the command line:
```
mogrify -format png -transparent "#fc00fc" *.tga; rm *.tga
```
