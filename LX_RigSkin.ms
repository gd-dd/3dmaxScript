-- Run this file in any Max instance. No LXTool connection is required.
global LXRigEntryRoot
LXRigEntryRoot = getFilenamePath (getSourceFileName())
fileIn (LXRigEntryRoot + "bridge\\rig_context.ms") quiet:true
python.ExecuteFile (LXRigEntryRoot + "bridge\\open_rig.py")
