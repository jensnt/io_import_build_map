# BUILD Map Importer - Blender Add-on
This Blender Add-on lets you import maps in the BUILD format used by games such as Blood or Duke Nukem 3D.

![E1L1](/images/e1l1.png)


## Installation

To install the Add-on you need [Blender](https://www.blender.org/) in version 2.93 or later.

1. Download the [latest Version](https://github.com/jensnt/io_import_build_map/releases/latest) from the Release Page. You need the file **io_import_build_map.zip**. 
3. Install the Add-on by opening the Blender Preferences and clicking on `Install…` button at the top of the "Add-ons" section.  
Then browse for the zip file you downloaded and click `Install Add-on`.
5. The Add-on will not be enabled automatically. You have to enable it by checking it's check box in the Add-ons list before you can use it.

![Preferences](/images/preferences.png)

4. The Add-on has it's own preferences where you can set the path to your texture folders.  
Here you can use the texture folder from the file **example-map-and-textures.zip** you can find in the [latest Version](https://github.com/jensnt/io_import_build_map/releases/latest).  
It contains a small set of free textures for the example map **SHOCK.MAP**.  
Or you can use textures from a game if you own a copy. See: [Getting original textures](https://github.com/jensnt/io_import_build_map#getting-original-textures)

#### All textures need to be PNG or JPG files and use one of the following numbering formats as name:
- As created by the Xtract tool: 056-002.png
- BUILD tile number as name: 0568.png (up to 8 leading zeros allowed)

## Import Options

![Import Options](/images/import-options.png)

The following Import Options are available:

- Object Prefix
  - This option specifies a prefix that will be used in the name of every imported object
- Split Sectors
  - If this is enabled, the floor and ceiling of every sector will be split off into a separate object.  
    This is necessary if you want custom properties saved for sectors.
- Split Walls
  - If this is enabled, all walls will be split off into separate objects.  
    This is neccessary if you want custom properties saved for walls.
- Split Sky
  - If this is enabled, floors and ceilings with parallaxing enabled will be split off into separate objects and sorted into the "Sky" collection.
- Scale Sprites as in Game
  - Some sprites are displayed in a different size in game compared to map editors.  
    If this option is enabled the importer will try to scale them as they appear in game.
- Wall Sprite Offset
  - This is useful to avoid Z-fighting for sprites that are placed right onto a wall.  
    A small offset like 0.01 is enough in many cases.
- Use Custom User Art
  - If a Custom User Art texture folder is specified in the preferences you can use this option to enable or disable the usage of Custom User Art textures.
- Reuse Materials
  - This option specifies if materials that already exist in your blender project with the same name should be reused.  
    If this is disabled new materials will be created with a suffix.
- Pixel Shading
  - This option makes textures render with hard pixel edges.
- Procedural Material Effects
  - If this is enabled the add-on will create additional shader nodes to generate a little more realistic appearance of the materials.  
    This works best with "Pixel Shading" disabled.
- Use Back Face Culling
  - This enables Back Face Culling for the created materials
- Ignore Map Errors
  - If you encounter a corrupted map that gives you errors where for example the number of sectors appears incorrect, you can try this option.  
    The importer will try to ignore corrupted parts of the map. No guarantee for success, though.

## Custom Properties

One feature of this Add-on is that it can save the original map data for every sector, wall and sprite into custom properties of those objects.
For Sectors and Walls you need to enable the Import options "Split Sectors" and "Split Walls" for this to work.
This allows for debugging maps or for reusing those properties in Blender.

![Custom Properties](/images/custom-props.png)

## Getting original textures

You can get textures from your original game as follows:

- You will need the .GRP file from your game.
- You need to get the Xtract tool for Windows.
  - You can get it either from here: [The ReBUILD Project](https://blood.sourceforge.net/rebuild.php)
  - Or from here: [RTCM - Files - Source Code BUILD Windows Tools and Engines](http://www.dukertcm.com/knowledge-base/downloads-rtcm/src-build-mod-win/) (HTTP only!) (look for: "ReBUILD Windows xtract")
- Next place the .GRP file and the Xtract tool in the same folder, open a command line in that folder and execute Xtract on the command line as follows:
```
.\Xtract.exe YOURGAME.GRP
```
- It will give you the textures as .tga files which you need to convert to png.
- You can use XnConvert to do that. Get it from here: [XnConvert · Batch Image Converter](https://www.xnview.com/en/xnconvert/#downloads)
  - In the "Input"-Tab: Add folder "tiles" that was generated by Xtract
  - In the "Actions"-Tab: Add action "Transparent color" (#fc00fc (Red:252; Green:0; Blue:252))
  - In the "Output"-Tab select the output folder
  - Set Format to "PNG - Portable Network Graphics"
  - Set Filename to just "{Filename}" without "_result"
- Alternatively you can do the same using [ImageMagick](https://imagemagick.org/) by executing the following in the command line:
```
mogrify -format png -transparent "#fc00fc" *.tga; rm *.tga
```
