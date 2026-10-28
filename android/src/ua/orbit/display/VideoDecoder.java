package ua.orbit.display;

import android.media.*;
import android.os.Build;
import android.view.Surface;
import java.io.IOException;
import java.nio.ByteBuffer;

/** Bounded by the host ACK window; no application video queue. */
final class VideoDecoder implements AutoCloseable {
    interface Listener { void frame(long sequence); void failed(); }
    private final MediaCodec codec;
    private final Surface surface;
    private final Thread drain;
    private volatile boolean stopped;
    static MediaCodecInfo candidate() {
        MediaCodecInfo fallback=null;
        for(MediaCodecInfo info:new MediaCodecList(MediaCodecList.REGULAR_CODECS).getCodecInfos()) {
            if(info.isEncoder())continue;
            for(String type:info.getSupportedTypes())if(type.equalsIgnoreCase("video/avc")) {
                boolean software=Build.VERSION.SDK_INT>=29?info.isSoftwareOnly():info.getName().startsWith("OMX.google.")||info.getName().startsWith("c2.android.");
                if(!software)return info;
                fallback=info;
            }
        }
        return fallback;
    }
    static boolean available(){try{return candidate()!=null;}catch(Exception e){return false;}}
    VideoDecoder(Surface output,int width,int height,Listener listener)throws Exception {
        surface=output;
        MediaCodecInfo info=candidate();
        if(info==null)throw new IOException("Немає H.264 декодера. Обери JPEG на ПК.");
        codec=MediaCodec.createByCodecName(info.getName());
        try {
            MediaFormat format=MediaFormat.createVideoFormat("video/avc",width,height);
            format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE,4*1024*1024);
            format.setInteger(MediaFormat.KEY_PRIORITY,0);
            if(Build.VERSION.SDK_INT>=30&&info.getCapabilitiesForType("video/avc").isFeatureSupported(MediaCodecInfo.CodecCapabilities.FEATURE_LowLatency))format.setInteger(MediaFormat.KEY_LOW_LATENCY,1);
            codec.configure(format,surface,null,0);codec.start();
        } catch(Exception e){codec.release();surface.release();throw e;}
        drain=new Thread(()->{
            MediaCodec.BufferInfo buffer=new MediaCodec.BufferInfo();
            try {
                while(!stopped) {
                    int index=codec.dequeueOutputBuffer(buffer,10000);
                    if(index>=0) {
                        long seq=buffer.presentationTimeUs;
                        boolean frame=(buffer.flags&MediaCodec.BUFFER_FLAG_CODEC_CONFIG)==0;
                        codec.releaseOutputBuffer(index,frame);
                        if(frame)listener.frame(seq);
                    }
                }
            }catch(Exception e){if(!stopped)listener.failed();}
        },"Orbit-video-output");
        drain.start();
    }
    void feed(byte[] packet,long seq)throws Exception {
        long deadline=System.nanoTime()+3000000000L;
        while(!stopped&&System.nanoTime()<deadline) {
            int index=codec.dequeueInputBuffer(10000);
            if(index<0)continue;
            ByteBuffer input=codec.getInputBuffer(index);
            if(input==null||input.capacity()<packet.length-9)throw new IOException("Кадр завеликий для декодера. Обери легший профіль на ПК.");
            input.clear();input.put(packet,9,packet.length-9);
            codec.queueInputBuffer(index,0,packet.length-9,seq,0);return;
        }
        throw new IOException("Декодер не відповідає. Спробуй JPEG у кроці «Якість» на ПК.");
    }
    public void close() {
        stopped=true;
        try{drain.join(1500);}catch(InterruptedException e){Thread.currentThread().interrupt();}
        try{codec.stop();}catch(Exception ignored){}
        codec.release();surface.release();
    }
}
