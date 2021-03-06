#!/usr/bin/python3

#
# Script to handle live streaming audio/video from platforms such as RPi2/3/Zero
#

# Imports

import os
import subprocess
import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

# Definitions

# Matt box stream
STREAM_URL= os.getenv('AV_STREAM_URL','rtmp://10.0.31.212/live')
STREAM_KEY=os.getenv('AV_STREAM_KEY','')

DISABLE_AUDIO=os.getenv('AV_DISABLE_AUDIO',0)
HAS_AUDIO=0
AUDIO_SAMPLING_RATE=os.getenv('AV_AUDIO_SAMPLING_RATE',16000)

# Set to empty if the v4l2src supports h.264 output, otherwise use h/w accelerated encoding
H264_ENCODER=''

AUDIO_SRC=os.getenv('AV_AUDIO_SRC', 'alsasrc device=hw:1')
AUDIO_BITRATE=os.getenv('AV_AUDIO_BITRATE',128)

VIDEO_SOURCE=os.getenv('AV_VIDEO_SOURCE','rpicamsrc keyframe-interval=2 hflip=true vflip=true')
#VIDEO_SOURCE="uvch264src initial-bitrate=5000000 average-bitrate=5000000 iframe-period=3000 device=/dev/video0 name=src auto-start=true"
#VIDEO_SOURCE="uvch264src device=/dev/video0 auto-start=true"
VIDEO_WIDTH=os.getenv('AV_VIDEO_WIDTH',1280)
VIDEO_HEIGHT=os.getenv('AV_VIDEO_HEIGHT',720)
VIDEO_FRAMERATE=os.getenv('AV_VIDEO_FRAMERATE',30)

H264_ENCODER_PARAMS = os.getenv('AV_H264_ENCODER_PARAMS', '')
H264_PARSER_PARAMS = os.getenv('AV_H264_PARSER_PARAMS', '')

# Support functions

def exists(path):
    """Test whether a path exists.  Returns False for broken symbolic links"""
    try:
        os.stat(path)
    except OSError:
        return False
    return True

def bus_call(bus, msg, *args):
    # print("BUSCALL", msg, msg.type, *args)
    if msg.type == Gst.MessageType.EOS:
        print("End-of-stream")
        loop.quit()
        return
    elif msg.type == Gst.MessageType.ERROR:
        print("GST ERROR", msg.parse_error())
        loop.quit()
        return
    return True

saturation = -100
def set_saturation(pipeline):
    global saturation
    if saturation <= 100:
      print("Setting saturation to {0}".format(saturation))
      videosrc.set_property("saturation", saturation)
      videosrc.set_property("annotation-text", "Saturation %d" % (saturation))
    else:
      pipeline.send_event (Gst.Event.new_eos())
      return False
    saturation += 10
    return True

# Main function
if __name__ == "__main__":

    # Detect platform specifics

    # Check if we have a v4l2src
    if exists('/dev/video0') :
        print("Detected webcam")
        VIDEO_SOURCE="v4l2src"
        # Assume for now we have audio (!)
        print('Assume webcam has audio')
        HAS_AUDIO=1
        # Check if the webcam outputs native h.264
        result = subprocess.run(['v4l2-ctl','--list-formats'], stdout=subprocess.PIPE)
        if "H264" not in str(result.stdout):
            print('Webcam does not support h.264')
            H264_ENCODER='omxh264enc ' + H264_ENCODER_PARAMS + ' ! '
        else:
            print('Webcam supports h.264')
    else:
        print("Defaulting to PiCam")
        HAS_AUDIO=0
        H264_ENCODER='omxh264enc ' + H264_ENCODER_PARAMS + ' ! '
        result = subprocess.run(['cat','/proc/asound/devices'], stdout=subprocess.PIPE)
        if "capture" not in str(result.stdout):
            print('No audio capture available')
        else:
            print('Audio capture available')
            HAS_AUDIO=1
            # Assume hardware device 1 (TODO: Work this out from result.stdout)
            AUDIO_DEVICE=1
            # Assume we can capture at 44100
            AUDIO_SAMPLING_RATE=44100

    # Initialization
    GObject.threads_init()
    loop = GObject.MainLoop()
    Gst.init(None)

    audiostr = AUDIO_SRC + " ! audio/x-raw, format=(string)S16LE, endianness=(int)1234, signed=(boolean)true, width=(int)16, depth=(int)16, rate=(int)" + str(AUDIO_SAMPLING_RATE) + " ! queue ! voaacenc bitrate=" + str(AUDIO_BITRATE) + " ! aacparse ! audio/mpeg,mpegversion=4,stream-format=raw ! queue ! mux. "
    videostr = VIDEO_SOURCE + " ! " + H264_ENCODER + " video/x-h264,profile=high,width=" +str(VIDEO_WIDTH) + ",height=" + str(VIDEO_HEIGHT) + ",framerate=" + str(VIDEO_FRAMERATE) + "/1 ! h264parse " + H264_PARSER_PARAMS + " ! "
    muxstr = "flvmux streamable=true name=mux ! queue ! "
    sinkstr = "rtmpsink location='" + STREAM_URL + "/" + STREAM_KEY + " live=1 flashver=FME/3.0%20(compatible;%20FMSc%201.0)'"

    if DISABLE_AUDIO == '1':
        HAS_AUDIO=0

    if HAS_AUDIO:
        # Audio + Video -> Restream.io
        pipelinestr = audiostr + videostr + muxstr + sinkstr
    else:
        # Video -> Restream.io
        pipelinestr = videostr + muxstr + sinkstr

    print("Pipeline stream:")
    print(pipelinestr)

    pipeline = Gst.parse_launch(pipelinestr)

    if pipeline == None:
        print ("Failed to create pipeline")
        sys.exit(0)

    # watch for messages on the pipeline's bus (note that this will only
    # work like this when a GLib main loop is running)
    bus = pipeline.get_bus()
    bus.add_watch(0, bus_call, loop)

# TODO: Changing parameters
#    videosrc = pipeline.get_by_name ("src")
#    videosrc.set_property("saturation", saturation)
#    videosrc.set_property("annotation-mode", 1)

#    sink = pipeline.get_by_name ("s")
#    sink.set_property ("location", "test.mp4")

    # this will call set_saturation every 1s
#    GObject.timeout_add(1000, set_saturation, pipeline)

    # Run the pipeline
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except Exception as e:
        print(e)

    # All done - cleanup
    pipeline.set_state(Gst.State.NULL)
