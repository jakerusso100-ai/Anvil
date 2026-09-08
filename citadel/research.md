# Citadel of Ricks — reference research log

This file records what the model is built from, what could not be obtained, and
the exact wording of every description used. It exists so the next revision can
be checked against sources instead of memory.

## What was reachable from this session

The session's egress policy ("Default – trusted network access") allows GitHub,
npm, PyPI and a few cloud-storage hosts and blocks everything else. Every image
route was tried and refused by the proxy (HTTP 403 on CONNECT):

- Fandom wikis (rickandmorty.fandom.com, static.wikia.nocookie.net, vignette.wikia, images.wikia) and the BreezeWiki / antifandom mirrors
- Wikipedia / Wikimedia (en, en.m, wikiwand, upload.wikimedia.org, dumps)
- Screencap engines: masterofallscience.com, frinkiac.com, morbotron.com
- TV metadata with episode stills: TVmaze, TMDB, TheTVDB, fanart.tv, Trakt, OMDb, IMDb media
- Image hosts / CDNs: imgur, reddit (i.redd.it, old.reddit), pinterest, tumblr, giphy, tenor, flickr, cloudinary, discord, googleusercontent, unsplash, wp.com, weserv/wsrv proxies
- 3D model sites (for their preview renders): Thingiverse, Printables, Cults3D, MyMiniFactory, Sketchfab, CGTrader, TurboSquid, Free3D, STLFinder, Yeggi, 3dmdb, Gumroad
- Search engines (bing/ddg/google/yandex images), archive.org, archive.ph, Wayback, Common Crawl index, Hugging Face, Kaggle, Sourcegraph, grep.app
- Social/art: DeviantArt, ArtStation, Behance, TikTok, Instagram, Facebook, X, Bluesky, Mastodon, KnowYourMeme
- Adult Swim / Max / Turner CDN, comicbook.com, screenrant, gamerant, TV Tropes static

GitHub public repositories clone fine. Ten Rick and Morty repos were pulled
(wiki apps, wallpaper collections, a Discord "Citadel_of_Ricks" bot, a 3D
tribute, an API image mirror, episode transcripts). None contains a still of
the Citadel exterior; the API mirror is character avatars only.

**Net result: no show frame, comic panel or fan render of the Citadel could be
viewed from this environment.** The geometry below is built from the written
descriptions in the next section and the author's recollection of the
establishing shot, and is labelled accordingly in the viewer.

To unblock a fully image-checked revision, either (a) commit reference stills
into `citadel/refs/` on this branch (GitHub is reachable, so they can be read
and compared frame-by-frame), or (b) run the session in an environment whose
network policy allows the Fandom wiki and image hosts.

## Written descriptions used (verbatim where available)

**Rick and Morty Wiki, "The Citadel"** (via search summaries):
> "The Citadel is located within an orange/brown nebulae, and is a massive space station with a central glass dome, with three separate, smaller domed districts protruding from it. Several metallic plates extend from the bottom, housing the machinery that keeps the Citadel stable and in orbit."
> "The interior of the Citadel has a mixture of metal structures and natural fauna, with numerous fountains, trees, and distinct curved buildings. Somewhere within the Citadel, a large statue depicting an unspecified Rick sits in a central column."

**Great Multiverse Wiki, "Citadel of Ricks"** (same text is quoted in the modelling log below):
> "The Citadel consists of a large, centralized pod surrounded by three smaller versions of this pod, and connected by a hybrid technical/organic bridge. There are also three legs extruding downward that allow the structure to stand on its own. Finally, there is a singular centralized antenna that can transmit various data to and from the Council of Ricks."

**robertatlas3100, "Project 1 – Citadel of Ricks" (2017 CAD build log).** The most
useful shape evidence, because it describes how the exterior was reproduced part
by part:
- "In order to create the main body of the Citadel, [we] first created a profile sketch of the main pod and revolved it around the center axis." → the pod is a **body of revolution**, not a flat disc plus hemisphere.
- "A new sketch was created, the original pod was copied and scaled up slightly, the sketch was extruded, and only the parts of the pod that intersected the sketch extrusion were kept, creating the raised piece that rests on the outside of the original pod." → a **raised band / shell** sits on the outside of the pod.
- "The new body was copied, moved a sufficient distance away, and scaled down to 60% to create the smaller pods." → satellite pods are **60 % copies** of the main pod.
- "The sculpt environment was used to create the bridge structure that runs from the main larger pod to the smaller pods." → bridges are **organic, sculpted** forms.
- "The pattern tool was used to create the trilateral symmetry that is found in the Citadel."
- "Sketches of the 'feet' were created and extruded to appropriate widths, then the pattern tool was utilized to create the other two feet."
- "For the middle antenna that runs right down the middle of the center pod, [we] decided to make this antenna shorter than the surrounding feet, so that, when printed, the model would be able to stand on its own." → the **antenna points downward** from the centre of the main pod, between the three feet, and is shorter than them.

**tato_713, "Citadel of Ricks scaled one in 200 thousand" (Thingiverse/Printables):**
> "There are many scenes where the Citadel is seen completely from the outside (episodes s1e10, s3e1 and s3e7), but it's always the same shot at the same angle, so some parts, their size and/or shape, are highly speculative, especially the lower part."
> "The center disk is about the size of Brooklyn when compared to New York City at the same scale. To calculate the size, [I] used a view of some buildings and a highway with some cars, extrapolating the size of the cars (~4 m)…"

## What the show says about it (transcripts, GitHub mirror of the fan transcripts)

S1E10 *Close Rick-counters of the Rick Kind*:
- Stage direction: "[Trans. Ext Citadel of Ricks]" then "[Trans. Int Citadel of Ricks…]" — the exterior establishing shot exists here.
- Rick C-137: "The citadel of Ricks. It's the secret headquarters for the council of Ricks."
- Rick C-137: "…a few thousand versions of me had the INGENIOUS IDEA OF BANDING TOGETHER like a herd of cattle or a school of fish…"
- Rick C-137: "You wanted to be safe from the government so you became a stupid government."

S3E01 *The Rickshank Rickdemption*:
- Morty: "It's the Citadel of Ricks. All the different Ricks from all the different realities got together to hide here from the government."
- Summer: "A city of Grandpas?"
- Teleportation Worker Rick: "This area's for teleporting the entire Citadel to somewhere else using only buttons and dials." → the station is a single teleportable structure.
- Quantum Rick: "The Citadel's been teleported to Federation space. It's doomed."

S3E07 *The Ricklantis Mixup* (via search summaries):
- Rick D. Sanchez III: "The Citadel was founded by Ricks for Ricks to be free."
- Cop Rick's suspect: "the Citadel is a lie, built on lies".

## How v2 differs from v1

| Feature | v1 (rejected) | v2 |
| --- | --- | --- |
| Hub | flat 17 km disc + hemisphere | single revolved pod: dome, raised collar, bowl-shaped hull tapering into a stack of metallic plates |
| Satellite districts | 39 % of hub, on stalks | 60 % scaled copies of the main pod (same profile) |
| Bridges | straight causeway + tube | thick sagging organic tube with ribs, plus a technical truss rail |
| Understructure | separate plate stack + keel | plates are part of each pod's own profile |
| Antenna | on top of the dome | runs down the middle of the main pod, shorter than the legs |
| Legs | from plate stack, between pods | from the main pod's lower plates, between pods, longer than the antenna |

Least-certain choices (one number each in `spec.json`): leg attachment point and
rake, bridge sag, plate count, and whether the satellite pods sit level with the
main pod.
