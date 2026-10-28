package ua.orbit.display;
import android.app.*;import android.content.*;import android.net.Uri;import android.os.*;import android.provider.Settings;import android.util.Base64;
import org.json.JSONObject;import java.io.*;import java.net.*;import java.security.*;import java.security.spec.X509EncodedKeySpec;

final class Updater {
    static final int VERSION=4;
    static final String MANIFEST="https://github.com/krekerhihle/orbit-display/releases/latest/download/update.json";
    static final String PREFIX="https://github.com/krekerhihle/orbit-display/releases/download/";
    private boolean busy,ready,offered;private long checked=-300000;
    synchronized void check(MainActivity activity){
        if(busy||SystemClock.elapsedRealtime()-checked<300000)return;
        checked=SystemClock.elapsedRealtime();busy=true;
        new Thread(()->{
            try{
                JSONObject envelope=new JSONObject(new String(read(MANIFEST,65536),"UTF-8"));
                byte[] payload=Base64.decode(envelope.getString("payload"),Base64.DEFAULT);
                Signature verifier=Signature.getInstance("SHA256withRSA");
                verifier.initVerify(KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(Base64.decode(UpdateKey.PUBLIC_KEY,Base64.DEFAULT))));
                verifier.update(payload);
                if(!verifier.verify(Base64.decode(envelope.getString("signature"),Base64.DEFAULT)))throw new IOException("Invalid release signature");
                JSONObject item=new JSONObject(new String(payload,"UTF-8")).getJSONObject("android");
                if(item.getInt("versionCode")<=VERSION)return;
                String url=item.getString("url"),hash=item.getString("sha256");long size=item.getLong("size");
                if(!url.startsWith(PREFIX)||size<1||size>100*1024*1024||!hash.matches("[0-9a-f]{64}"))throw new IOException("Invalid update");
                File part=new File(activity.getCacheDir(),"orbit-update.part"),apk=new File(activity.getCacheDir(),"orbit-update.apk");
                MessageDigest digest=MessageDigest.getInstance("SHA-256");long count=0;
                try(InputStream in=open(url);OutputStream out=new FileOutputStream(part)){
                    byte[] b=new byte[65536];int n;while((n=in.read(b))!=-1){count+=n;if(count>size)throw new IOException("Oversized update");out.write(b,0,n);digest.update(b,0,n);}
                }
                StringBuilder hex=new StringBuilder();for(byte b:digest.digest())hex.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
                if(count!=size||!hash.equals(hex.toString())){part.delete();throw new IOException("Invalid checksum");}
                if(!part.renameTo(apk))throw new IOException("Cannot save update");
                synchronized(this){ready=true;}
                activity.runOnUiThread(()->offer(activity));
            }catch(Exception ignored){}finally{synchronized(this){busy=false;}}
        },"Orbit-updates").start();
    }
    static InputStream open(String url)throws IOException{
        URL target=new URL(url);if(!target.getProtocol().equals("https"))throw new IOException("HTTPS required");
        HttpURLConnection c=(HttpURLConnection)target.openConnection();c.setConnectTimeout(15000);c.setReadTimeout(30000);c.setRequestProperty("User-Agent","Orbit-Display/0.4.0");
        InputStream stream=c.getInputStream();
        if(!c.getURL().getProtocol().equals("https")){stream.close();throw new IOException("HTTPS required");}
        return stream;
    }
    static byte[] read(String url,int maximum)throws IOException{
        try(InputStream in=open(url);ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){if(out.size()+n>maximum)throw new IOException("Too large");out.write(b,0,n);}return out.toByteArray();
        }
    }
    synchronized void offer(MainActivity activity){
        if(!ready||offered||activity.isFinishing()||!activity.resumed||activity.connected||activity.connecting)return;offered=true;
        new AlertDialog.Builder(activity).setTitle("Оновлення Orbit готове")
            .setMessage("Новий APK завантажено й перевірено. Android попросить підтвердити встановлення.")
            .setPositiveButton("Встановити",(d,w)->install(activity)).setNegativeButton("Пізніше",(d,w)->offered=false).show();
    }
    void install(Activity activity){
        offered=false;
        if(Build.VERSION.SDK_INT>=26&&!activity.getPackageManager().canRequestPackageInstalls()){
            activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+activity.getPackageName())));return;
        }
        activity.startActivity(new Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("content://ua.orbit.display.updates/update.apk"),"application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));
    }
}
