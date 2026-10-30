-- A token belongs to the current scene, not the lifetime of a UI window.
global LXRigSceneToken
if LXRigSceneToken == undefined do LXRigSceneToken = ((dotNetClass "System.Guid").NewGuid()).ToString()
callbacks.removeScripts id:#LXRigScene
for event in #(#filePostOpen, #systemPostNew, #systemPostReset) do
    callbacks.addScript event "LXRigSceneToken = ((dotNetClass \"System.Guid\").NewGuid()).ToString()" id:#LXRigScene
