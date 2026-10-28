package ua.orbit.display;

import android.app.*;
import android.os.*;
import android.content.*;
import android.content.res.Configuration;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.ByteBuffer;
import java.security.*;
import java.security.cert.X509Certificate;
import java.util.Locale;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.net.ssl.*;

public final class MainActivity extends Activity {
    static final int BG=Color.rgb(16,16,16), CARD=Color.rgb(25,25,25), MINT=Color.WHITE, TEXT=Color.rgb(245,245,245), MUTED=Color.rgb(170,170,170);
    static final int PORT=48620, MAX_FRAME=16*1024*1024;
    final Handler ui=new Handler(Looper.getMainLooper());
    final ExecutorService connector=Executors.newSingleThreadExecutor();
    final ScheduledExecutorService clock=Executors.newSingleThreadScheduledExecutor();
    final Updater updater=new Updater();
    boolean resumed=false;
    SharedPreferences prefs;
    LinearLayout root;
    EditText host,pin;
    TextView status,stats;
    Button connect;
    boolean usb=false, immersive=false;
    volatile boolean connecting=false, connected=false;
    volatile Link link;
    ScreenView screen;
    boolean videoMode=false;int videoWidth,videoHeight;
    int homeStep=0; String enteredHost="",enteredPin="";
    LinearLayout toolbar;
    volatile long generation=0;
    boolean touchAllowed=true, clipboardAllowed=false;
    float displayHz=60, maximumHz=60;
    double networkMbps=0;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        prefs=getSharedPreferences("orbit",MODE_PRIVATE);
        showHome("Почнімо зі способу підключення");
        clock.scheduleAtFixedRate(()->ui.post(()->{if(resumed&&!connected&&!connecting){updater.check(this);updater.offer(this);}}),5,300,TimeUnit.SECONDS);
        clock.scheduleAtFixedRate(()->{if(connected)ui.post(()->{if(connected){displayHz=getWindowManager().getDefaultDisplay().getRefreshRate();send(json("type","refresh","hz",displayHz));}});},1,1,TimeUnit.SECONDS);
    }
    int dp(float n){return (int)(getResources().getDisplayMetrics().density*n+.5f);}
    GradientDrawable bg(int color,int radius){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));return d;}
    TextView text(String s,int size,int color){TextView v=new TextView(this);v.setText(s);v.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));v.setTextSize(size);v.setTextColor(color);v.setPadding(0,dp(5),0,dp(5));return v;}
    LinearLayout column(){LinearLayout v=new LinearLayout(this);v.setOrientation(LinearLayout.VERTICAL);return v;}
    void space(LinearLayout p,int h){View v=new View(this);p.addView(v,new LinearLayout.LayoutParams(1,dp(h)));}
    Button button(String s,boolean primary,Runnable action){Button b=new Button(this);b.setText(s);b.setTextSize(14);b.setAllCaps(false);b.setTextColor(primary?BG:TEXT);b.setBackground(bg(primary?MINT:Color.rgb(45,45,45),12));b.setPadding(dp(14),dp(10),dp(14),dp(10));b.setMinHeight(dp(48));b.setOnClickListener(v->action.run());return b;}
    void setRoot(View content){
        root=column();root.setBackgroundColor(BG);root.addView(content,new LinearLayout.LayoutParams(-1,-1));
        root.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
        setContentView(root);root.requestApplyInsets();
    }
    EditText field(String hint,boolean numeric){EditText e=new EditText(this);e.setSingleLine(true);e.setTextSize(18);e.setTextColor(TEXT);e.setHintTextColor(MUTED);e.setHint(hint);e.setPadding(dp(14),dp(12),dp(14),dp(12));e.setBackground(bg(BG,10));e.setInputType(numeric?InputType.TYPE_CLASS_NUMBER:InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);return e;}
    void showHome(String message){
        immersive=false;getWindow().getDecorView().setSystemUiVisibility(0);getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        screen=null;toolbar=null;
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);
        LinearLayout page=column();page.setPadding(dp(24),dp(22),dp(24),dp(24));scroll.addView(page);
        TextView brand=text("ORBIT  /  DISPLAY",13,MINT);brand.setLetterSpacing(.14f);page.addView(brand);space(page,16);
        page.addView(text(new String[]{"З'єднай пристрої.","Підготуй ноутбук.","Запусти свій екран."}[homeStep],28,TEXT));
        page.addView(text("КРОК "+(homeStep+1)+" / 3",12,MUTED));space(page,16);
        LinearLayout card=column();card.setPadding(dp(20),dp(18),dp(20),dp(20));card.setBackground(bg(CARD,20));page.addView(card);
        // Fields persist across wizard steps without storing the session PIN on disk.
        host=field("192.168.1.10",false);host.setText(usb?"127.0.0.1":enteredHost.isEmpty()?prefs.getString("host",""):enteredHost);
        pin=field("Код із 6 цифр",true);pin.setText(enteredPin);pin.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(6)});
        connect=button("Підключити екран →",true,()->begin());
        if(homeStep==0){
            card.addView(text("ОБЕРИ ПІДКЛЮЧЕННЯ",12,TEXT));
            card.addView(button("USB-кабель · рекомендовано",usb,()->{usb=true;homeStep=1;showHome("Під'єднай кабель із передаванням даних.");}));space(card,12);
            card.addView(button("Wi-Fi / USB-модем",!usb,()->{usb=false;homeStep=1;showHome("Підключи пристрої до однієї мережі.");}));
        }else if(homeStep==1){
            card.addView(text(usb?"1. Під'єднай USB-кабель.\n\n2. У параметрах розробника увімкни налагодження через USB та дозволь доступ цьому ПК.\n\n3. В Orbit на Windows пройди кроки до «Запуск» і почни сеанс.":"1. Підключи ноутбук і телефон до однієї мережі або ввімкни USB-модем.\n\n2. В Orbit на Windows обери Wi-Fi / USB-модем.\n\n3. Пройди налаштування до «Запуск» і почни сеанс.",16,TEXT));space(card,12);
            card.addView(button("На ПК вже є код →",true,()->{homeStep=2;showHome("Введи код, який показує Orbit на ноутбуці.");}));
        }else{
            card.addView(text(usb?"USB · адреса визначена автоматично":"Адреса ноутбука з Orbit на Windows",14,MUTED));
            host.setEnabled(!usb);card.addView(host);space(card,12);
            card.addView(text("Шестизначний код із програми на ПК",14,MUTED));card.addView(pin);space(card,18);card.addView(connect);
        }
        status=text(message,14,MUTED);card.addView(status);
        if(homeStep>0){space(page,14);page.addView(button("← Назад",false,()->{enteredHost=host.getText().toString();enteredPin=pin.getText().toString();homeStep--;showHome("Продовж налаштування.");}));}
        space(page,22);
        page.addView(button("Як підключити?",false,()->new AlertDialog.Builder(this).setTitle("Три кроки")
            .setMessage("1. На Windows відкрийте Orbit Display. Додайте віртуальний монітор і виберіть його.\n\n2. Wi-Fi: під'єднайте пристрої до однієї мережі та введіть IP ноутбука. USB: увімкніть USB debugging і натисніть «Підготувати USB» на ПК.\n\n3. Почніть сеанс на ПК, введіть код тут. Звірте відбиток ПК при першому з'єднанні.\n\nУ перегляді: один палець — миша / перетягування; два — прокрутка. «Текст» відкриває клавіатуру. Кнопка «⋯» — буфер, Enter, Esc, ПКМ і повний екран. Для виходу з повного екрана натисніть «Назад».")
            .setPositiveButton("Зрозуміло",null).show()));
        space(page,18);page.addView(text("USB-A або USB-C з передаванням даних.\nFull HD · запит максимальної герцовки · TLS\nOrbit 0.4 · Android 8+",12,MUTED));setRoot(scroll);
    }
    void begin(){
        if(connecting||connected)return;
        String address=host.getText().toString().trim(),code=pin.getText().toString();
        if(!address.matches("[a-zA-Z0-9._-]{1,253}")||!code.matches("[0-9]{6}")){status.setText("Введіть IP / ім'я ПК без порту та код із 6 цифр.");return;}
        if(!usb)prefs.edit().putString("host",address).apply();
        connecting=true;connect.setEnabled(false);status.setText("Підключення…");
        requestFastDisplay();
        final float initialHz=displayHz;
        long epoch=++generation;
        connector.execute(()->{
            Link attempt=new Link(address,epoch);link=attempt;
            try{
                attempt.open();
                if(epoch!=generation)throw new IOException("Скасовано");
                String saved=prefs.getString("cert:"+address,"");
                if(!attempt.fingerprint.equals(saved)&&!confirmCertificate(attempt.fingerprint,!saved.isEmpty(),epoch))throw new IOException("Відбиток не підтверджено");
                attempt.write(json("type","auth","version",1,"pin",code,"name",Build.MANUFACTURER+" "+Build.MODEL,"frame_ack_v2",true,"h264",VideoDecoder.available(),"refresh_hz",initialHz));
                JSONObject ready=attempt.readJson();
                if(!"ready".equals(ready.optString("type")))throw new IOException(ready.optString("message","ПК відхилив з'єднання"));
                if(ready.optInt("version")!=1)throw new IOException("Несумісна версія Orbit");
                prefs.edit().putString("cert:"+address,attempt.fingerprint).apply();
                attempt.video=ready.optString("codec").equals("h264");
                attempt.width=ready.optInt("video_width");attempt.height=ready.optInt("video_height");
                if(attempt.video&&(attempt.width<2||attempt.height<2||(long)attempt.width*attempt.height>16000000))throw new IOException("Некоректний розмір відео");
                ui.post(()->{if(epoch!=generation)return;videoMode=attempt.video;videoWidth=attempt.width;videoHeight=attempt.height;connecting=false;connected=true;touchAllowed=ready.optBoolean("touch");clipboardAllowed=ready.optBoolean("clipboard");showStream();});
                try{attempt.readFrames();}finally{attempt.releaseVideo();}
            }catch(Exception e){ui.post(()->{if(epoch==generation){disconnect();showHome("Не підключено: "+friendly(e));}});}
            finally{attempt.close();}
        });
    }
    String friendly(Exception e){if(e instanceof ConnectException)return usb?"USB ще не готовий. На ПК натисни «Перевірити USB», дозволь налагодження на телефоні та почни сеанс.":"ПК не приймає з’єднання. Почни сеанс в Orbit на Windows і перевір адресу.";if(e instanceof SocketTimeoutException)return "Час очікування минув. Перевірте адресу, мережу й брандмауер Windows.";String s=e.getMessage();return s==null?e.getClass().getSimpleName():s;}
    boolean confirmCertificate(String fingerprint,boolean changed,long epoch)throws InterruptedException{
        CountDownLatch latch=new CountDownLatch(1);AtomicBoolean accepted=new AtomicBoolean(false);
        ui.post(()->{if(epoch!=generation){latch.countDown();return;}new AlertDialog.Builder(this)
            .setTitle(changed?"Відбиток ПК змінився":"Перевірте цей ноутбук")
            .setMessage((changed?"Сертифікат відрізняється від збереженого. Продовжуйте тільки після перевірки на ПК.\n\n":"Порівняйте ці 4 групи з «Відбиток ПК» у програмі Windows:\n\n")+shortFingerprint(fingerprint)+"\n\nSHA-256:\n"+fingerprint)
            .setPositiveButton("Збігається",(d,w)->{accepted.set(true);latch.countDown();})
            .setNegativeButton("Скасувати",(d,w)->latch.countDown())
            .setOnCancelListener(d->latch.countDown()).show();});
        return latch.await(55,TimeUnit.SECONDS)&&accepted.get()&&epoch==generation;
    }
    String shortFingerprint(String f){return f.substring(0,4)+" "+f.substring(4,8)+" "+f.substring(8,12)+" "+f.substring(12,16);}
    void requestFastDisplay(){
        Display display=getWindowManager().getDefaultDisplay();Display.Mode active=display.getMode(),best=active;
        for(Display.Mode mode:display.getSupportedModes())if(mode.getPhysicalWidth()==active.getPhysicalWidth()&&mode.getPhysicalHeight()==active.getPhysicalHeight()&&mode.getRefreshRate()>best.getRefreshRate())best=mode;
        maximumHz=best.getRefreshRate();displayHz=display.getRefreshRate();
        WindowManager.LayoutParams params=getWindow().getAttributes();
        params.preferredDisplayModeId=best.getModeId();params.preferredRefreshRate=maximumHz;
        if(Build.VERSION.SDK_INT>=30)params.preferMinimalPostProcessing=true;
        getWindow().setAttributes(params);
    }
    void showStream(){
        android.view.inputmethod.InputMethodManager ime=(android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE);
        if(root!=null)ime.hideSoftInputFromWindow(root.getWindowToken(),0);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout page=column();page.setBackgroundColor(Color.BLACK);
        toolbar=new LinearLayout(this);toolbar.setGravity(Gravity.CENTER_VERTICAL);toolbar.setPadding(dp(8),dp(4),dp(8),dp(4));toolbar.setBackgroundColor(CARD);
        Button back=button("×",false,()->{disconnect();showHome("Сеанс завершено");});toolbar.addView(back,new LinearLayout.LayoutParams(dp(48),dp(44)));
        stats=text("ORBIT · з'єднано",12,MINT);stats.setPadding(dp(10),0,dp(8),0);toolbar.addView(stats,new LinearLayout.LayoutParams(0,-2,1));
        Button type=button("Текст",false,()->textDialog());toolbar.addView(type,new LinearLayout.LayoutParams(dp(78),dp(44)));
        Button more=button("⋯",false,()->menu());toolbar.addView(more,new LinearLayout.LayoutParams(dp(52),dp(44)));page.addView(toolbar);
        screen=new ScreenView();
        FrameLayout viewport=new FrameLayout(this);viewport.setBackgroundColor(Color.BLACK);
        if(videoMode){
            final Link owner=link;
            TextureView texture=new TextureView(this);texture.setOpaque(false);
            texture.setSurfaceTextureListener(new TextureView.SurfaceTextureListener(){
                public void onSurfaceTextureAvailable(SurfaceTexture t,int w,int h){fitVideo(texture,w,h);owner.surface=new Surface(t);owner.surfaceReady.countDown();}
                public void onSurfaceTextureSizeChanged(SurfaceTexture t,int w,int h){fitVideo(texture,w,h);}
                public boolean onSurfaceTextureDestroyed(SurfaceTexture t){owner.close();return true;}
                public void onSurfaceTextureUpdated(SurfaceTexture t){}
            });
            viewport.addView(texture,new FrameLayout.LayoutParams(-1,-1));
        }
        viewport.addView(screen,new FrameLayout.LayoutParams(-1,-1));page.addView(viewport,new LinearLayout.LayoutParams(-1,0,1));setRoot(page);screen.requestFocus();
    }
    void fitVideo(TextureView texture,int width,int height){
        float scale=Math.min((float)width/videoWidth,(float)height/videoHeight);
        Matrix matrix=new Matrix();matrix.setScale(videoWidth*scale/width,videoHeight*scale/height,width/2f,height/2f);texture.setTransform(matrix);
    }
    void menu(){
        String[] items={"Повний екран","Enter","Esc","Tab","Ctrl+C","Ctrl+V","Правий клік у центрі","Буфер Android → ПК","Буфер ПК → Android"};
        new AlertDialog.Builder(this).setTitle("Керування").setItems(items,(d,index)->{
            if(index==0){immersive=true;toolbar.setVisibility(View.GONE);getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);}
            else if(index==1)tapKey("enter");else if(index==2)tapKey("escape");else if(index==3)tapKey("tab");
            else if(index==4)chord("C");else if(index==5)chord("V");
            else if(index==6){pointer(.5f,.5f,"down","right");pointer(.5f,.5f,"up","right");}
            else if(!clipboardAllowed)toast("Дозвольте обмін буфером у програмі на ПК.");
            else if(index==7){android.content.ClipboardManager cm=(android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE);if(cm.hasPrimaryClip()){CharSequence t=cm.getPrimaryClip().getItemAt(0).coerceToText(this);String s=t==null?"":t.toString();if(s.length()>4096){toast("Максимум 4096 символів");return;}send(json("type","clipboard_set","text",s));toast("Текст надіслано");}}
            else if(index==8)send(json("type","clipboard_get"));
        }).show();
    }
    void textDialog(){if(!touchAllowed){toast("Керування вимкнено на ПК");return;}EditText input=field("Текст для активного вікна ПК",false);input.setSingleLine(false);input.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);input.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(4096)});
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Ввести на ноутбуці").setView(input).setPositiveButton("Ввести",(d,w)->send(json("type","text","text",input.getText().toString()))).setNegativeButton("Скасувати",null).create();
        dialog.setOnShowListener(d->{input.requestFocus();dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE);});dialog.show();}
    void toast(String s){Toast.makeText(this,s,Toast.LENGTH_LONG).show();}
    void tapKey(String key){if(!touchAllowed)return;send(json("type","key","key",key,"down",true));send(json("type","key","key",key,"down",false));}
    void chord(String key){if(!touchAllowed)return;send(json("type","key","key","ctrl","down",true));tapKey(key);send(json("type","key","key","ctrl","down",false));}
    void pointer(float x,float y,String action,String button){if(touchAllowed)send(json("type","pointer","x",(double)x,"y",(double)y,"action",action,"button",button));}
    static JSONObject json(Object... args){JSONObject obj=new JSONObject();try{for(int i=0;i<args.length;i+=2)obj.put((String)args[i],args[i+1]);}catch(Exception e){throw new IllegalArgumentException(e);}return obj;}
    void send(JSONObject value){Link current=link;if(current!=null&&connected)current.enqueue(value);}
    void disconnect(){generation++;connected=false;connecting=false;Link current=link;link=null;if(current!=null)current.close();getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);WindowManager.LayoutParams params=getWindow().getAttributes();params.preferredDisplayModeId=0;params.preferredRefreshRate=0;if(Build.VERSION.SDK_INT>=30)params.preferMinimalPostProcessing=false;getWindow().setAttributes(params);}
    @Override public void onBackPressed(){if(immersive&&toolbar!=null){immersive=false;toolbar.setVisibility(View.VISIBLE);getWindow().getDecorView().setSystemUiVisibility(0);return;}if(connected||connecting){disconnect();showHome("Сеанс завершено");}else super.onBackPressed();}
    @Override public void onResume(){super.onResume();resumed=true;if(!connected&&!connecting){updater.check(this);updater.offer(this);}}
    @Override public void onPause(){resumed=false;super.onPause();if(connected||connecting){disconnect();showHome("Сеанс призупинено. Підключіться знову.");}}
    @Override public void onDestroy(){disconnect();connector.shutdownNow();clock.shutdownNow();super.onDestroy();}

    final class Link {
        final String address;final long epoch;volatile SSLSocket socket;volatile Socket raw;DataInputStream in;DataOutputStream out;String fingerprint;
        boolean video;int width,height;volatile Surface surface;VideoDecoder decoder;
        final CountDownLatch surfaceReady=new CountDownLatch(1);
        long renderStart=SystemClock.elapsedRealtime();int renderFrames;
        void releaseVideo(){if(decoder!=null){decoder.close();decoder=null;}else if(surface!=null)surface.release();}
        final AtomicBoolean closed=new AtomicBoolean(false);
        final ThreadPoolExecutor sender=new ThreadPoolExecutor(1,1,0L,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<Runnable>(128));
        Link(String a,long e){address=a;epoch=e;}
        void open()throws Exception{
            // Trust is established by comparing the fingerprint BEFORE any auth secret is sent.
            TrustManager[] verifier={new X509TrustManager(){public X509Certificate[]getAcceptedIssuers(){return new X509Certificate[0];}public void checkClientTrusted(X509Certificate[]c,String a){}public void checkServerTrusted(X509Certificate[]c,String a)throws java.security.cert.CertificateException{if(c.length==0)throw new java.security.cert.CertificateException("No certificate");c[0].checkValidity();}}};
            SSLContext context=SSLContext.getInstance("TLS");context.init(null,verifier,new SecureRandom());
            raw=new Socket();raw.connect(new InetSocketAddress(address,PORT),8000);raw.setTcpNoDelay(true);
            if(closed.get())throw new IOException("Скасовано");
            socket=(SSLSocket)context.getSocketFactory().createSocket(raw,address,PORT,true);socket.setSoTimeout(12000);
            socket.setEnabledProtocols(new String[]{"TLSv1.2"});socket.startHandshake();
            byte[] digest=MessageDigest.getInstance("SHA-256").digest(socket.getSession().getPeerCertificates()[0].getEncoded());StringBuilder hex=new StringBuilder();for(byte b:digest)hex.append(String.format(Locale.ROOT,"%02X",b&255));fingerprint=hex.toString();
            in=new DataInputStream(new BufferedInputStream(socket.getInputStream()));out=new DataOutputStream(new BufferedOutputStream(socket.getOutputStream()));
        }
        synchronized void write(JSONObject obj)throws IOException{if(closed.get())throw new IOException("Закрито");byte[] bytes=obj.toString().getBytes(StandardCharsets.UTF_8);if(bytes.length>32767)throw new IOException("Команда завелика");out.writeInt(bytes.length+1);out.writeByte('J');out.write(bytes);out.flush();}
        void enqueue(JSONObject obj){if(closed.get())return;try{sender.execute(()->{try{write(obj);}catch(IOException e){close();}});}catch(RejectedExecutionException e){close();}}
        byte[] readPacket()throws IOException{int n=in.readInt();if(n<2||n>MAX_FRAME)throw new IOException("Некоректний розмір кадру");byte[] b=new byte[n];in.readFully(b);return b;}
        JSONObject parse(byte[] p)throws Exception{if(p[0]!='J'||p.length>32768)throw new IOException("Некоректна команда ПК");return new JSONObject(new String(p,1,p.length-1,StandardCharsets.UTF_8));}
        JSONObject readJson()throws Exception{return parse(readPacket());}
        void readFrames()throws Exception{
            if(video){
                if(!surfaceReady.await(8,TimeUnit.SECONDS)||closed.get())throw new IOException("Не вдалося відкрити екран відео");
                decoder=new VideoDecoder(surface,width,height,new VideoDecoder.Listener(){
                    public void frame(long sequence){
                        acknowledge(sequence,true);renderFrames++;long now=SystemClock.elapsedRealtime();
                        if(now-renderStart>=1000){final double fps=renderFrames*1000.0/(now-renderStart);renderFrames=0;renderStart=now;ui.post(()->{if(epoch==generation&&stats!=null)stats.setText(String.format(Locale.ROOT,"H.264 · %.0f FPS · %.0f Гц\n%.1f Мбіт/с",fps,displayHz,networkMbps));});}
                    }
                    public void failed(){close();}
                });
            }
            long start=SystemClock.elapsedRealtime(),bytes=0;int frames=0;
            while(!closed.get()){
                byte[] p=readPacket();
                if(p[0]=='H'){
                    if(!video||p.length<10)throw new IOException("Некоректний відеокадр");
                    long sequence=ByteBuffer.wrap(p,1,8).getLong();if(sequence<=0)throw new IOException("Некоректний номер кадру");
                    decoder.feed(p,sequence);bytes+=p.length;long now=SystemClock.elapsedRealtime();
                    if(now-start>=1000){final double mbps=bytes*.008/(now-start);ui.post(()->{if(epoch==generation)networkMbps=mbps;});bytes=0;start=now;}
                }else if(p[0]=='F'||p[0]=='G'){
                    int offset=p[0]=='G'?9:1;if(p.length<=offset)throw new IOException("Порожній кадр");
                    final long sequence=p[0]=='G'?ByteBuffer.wrap(p,1,8).getLong():0;
                    if(sequence<0)throw new IOException("Некоректний номер кадру");
                    BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(p,offset,p.length-offset,bounds);
                    if(bounds.outWidth<=0||bounds.outHeight<=0||(long)bounds.outWidth*bounds.outHeight>16000000)throw new IOException("Некоректні розміри кадру");
                    Bitmap frame=BitmapFactory.decodeByteArray(p,offset,p.length-offset);if(frame==null)throw new IOException("Не вдалося декодувати кадр");
                    ui.post(()->{if(epoch==generation&&screen!=null){screen.setFrame(frame,sequence,this);}else frame.recycle();});
                    frames++;bytes+=p.length;long now=SystemClock.elapsedRealtime();if(now-start>=1000){double mbps=bytes*.008/(now-start);ui.post(()->{if(epoch==generation)networkMbps=mbps;});frames=0;bytes=0;start=now;}
                }else{
                    JSONObject msg=parse(p);String kind=msg.optString("type");
                    if(kind.equals("clipboard")){String content=msg.optString("text");ui.post(()->{if(epoch==generation&&clipboardAllowed){((android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("Orbit",content));toast("Текст скопійовано з ПК");}});}
                    else if(kind.equals("permissions"))ui.post(()->{if(epoch==generation){touchAllowed=msg.optBoolean("touch");clipboardAllowed=msg.optBoolean("clipboard");}});
                    else if(kind.equals("error"))throw new IOException(msg.optString("message"));
                }
            }
            throw new IOException("З'єднання закрито");
        }
        void close(){if(!closed.compareAndSet(false,true))return;sender.shutdownNow();try{if(socket!=null)socket.close();}catch(IOException ignored){}try{if(raw!=null)raw.close();}catch(IOException ignored){}}
        void acknowledge(long sequence,boolean presented){enqueue(sequence==0?json("type","ack"):json("type","ack","seq",sequence,"presented",presented));}
    }

    final class ScreenView extends View {
        Bitmap frame;final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG|Paint.FILTER_BITMAP_FLAG);final RectF dest=new RectF();boolean pressed=false,scrolling=false;float lastY,lastX,lastNormY;long lastMove;
        ScreenView(){super(MainActivity.this);setFocusableInTouchMode(true);setBackgroundColor(videoMode?Color.TRANSPARENT:Color.BLACK);}
        Link frameLink;long frameSequence,drawStart=SystemClock.elapsedRealtime();int drawn=0;boolean pendingAck=false;
        void setFrame(Bitmap next,long sequence,Link source){if(pendingAck&&frameLink!=null)frameLink.acknowledge(frameSequence,false);frame=next;frameSequence=sequence;frameLink=source;pendingAck=true;postInvalidateOnAnimation();/* Never recycle a bitmap still referenced by the hardware renderer. */}
        @Override protected void onDraw(Canvas c){if(videoMode){float scale=Math.min((float)getWidth()/videoWidth,(float)getHeight()/videoHeight);float w=videoWidth*scale,h=videoHeight*scale;dest.set((getWidth()-w)/2,(getHeight()-h)/2,(getWidth()+w)/2,(getHeight()+h)/2);return;}if(frame==null)return;float scale=Math.min((float)getWidth()/frame.getWidth(),(float)getHeight()/frame.getHeight());float w=frame.getWidth()*scale,h=frame.getHeight()*scale;dest.set((getWidth()-w)/2,(getHeight()-h)/2,(getWidth()+w)/2,(getHeight()+h)/2);c.drawBitmap(frame,null,dest,paint);
            if(pendingAck){pendingAck=false;frameLink.acknowledge(frameSequence,true);drawn++;long now=SystemClock.elapsedRealtime();if(now-drawStart>=1000){if(stats!=null)stats.setText(String.format(Locale.ROOT,"%.0f FPS · %.0f Гц\n%.1f Мбіт/с",drawn*1000.0/(now-drawStart),displayHz,networkMbps));drawn=0;drawStart=now;}}
        }
        @Override public boolean onTouchEvent(android.view.MotionEvent e){
            if((frame==null&&!videoMode)||dest.isEmpty()||!touchAllowed)return true;int action=e.getActionMasked();float x=(e.getX()-dest.left)/dest.width(),y=(e.getY()-dest.top)/dest.height();x=Math.max(0,Math.min(1,x));y=Math.max(0,Math.min(1,y));
            if(action==MotionEvent.ACTION_DOWN){if(!dest.contains(e.getX(),e.getY()))return false;pressed=true;scrolling=false;lastX=x;lastNormY=y;pointer(x,y,"down","left");return true;}
            if(action==MotionEvent.ACTION_POINTER_DOWN){if(pressed)pointer(lastX,lastNormY,"up","left");pressed=false;scrolling=true;lastY=e.getY();return true;}
            if(action==MotionEvent.ACTION_MOVE){if(scrolling&&e.getPointerCount()>=2){float delta=e.getY()-lastY;if(Math.abs(delta)>dp(8)){send(json("type","scroll","amount",delta>0?120:-120));lastY=e.getY();}}else if(pressed&&SystemClock.elapsedRealtime()-lastMove>Math.max(4,1000/displayHz)){pointer(x,y,"move","left");lastX=x;lastNormY=y;lastMove=SystemClock.elapsedRealtime();}return true;}
            if(action==MotionEvent.ACTION_UP||action==MotionEvent.ACTION_CANCEL){if(pressed)pointer(x,y,"up","left");pressed=false;scrolling=false;return true;}return true;
        }
        String keyName(int code){switch(code){case KeyEvent.KEYCODE_ENTER:return "enter";case KeyEvent.KEYCODE_DEL:return "backspace";case KeyEvent.KEYCODE_ESCAPE:return "escape";case KeyEvent.KEYCODE_TAB:return "tab";case KeyEvent.KEYCODE_DPAD_LEFT:return "left";case KeyEvent.KEYCODE_DPAD_RIGHT:return "right";case KeyEvent.KEYCODE_DPAD_UP:return "up";case KeyEvent.KEYCODE_DPAD_DOWN:return "down";case KeyEvent.KEYCODE_CTRL_LEFT:case KeyEvent.KEYCODE_CTRL_RIGHT:return "ctrl";case KeyEvent.KEYCODE_ALT_LEFT:case KeyEvent.KEYCODE_ALT_RIGHT:return "alt";case KeyEvent.KEYCODE_SHIFT_LEFT:case KeyEvent.KEYCODE_SHIFT_RIGHT:return "shift";default:return null;}}
        @Override public boolean onKeyDown(int code,KeyEvent event){if(!touchAllowed)return super.onKeyDown(code,event);String name=keyName(code);if(name!=null){send(json("type","key","key",name,"down",true));return true;}if(event.isCtrlPressed()&&code>=KeyEvent.KEYCODE_A&&code<=KeyEvent.KEYCODE_Z){send(json("type","key","key",String.valueOf((char)('A'+code-KeyEvent.KEYCODE_A)),"down",true));return true;}int unicode=event.getUnicodeChar();if(unicode>0){send(json("type","text","text",new String(Character.toChars(unicode))));return true;}return super.onKeyDown(code,event);}
        @Override public boolean onKeyUp(int code,KeyEvent event){String name=keyName(code);if(name!=null&&touchAllowed){send(json("type","key","key",name,"down",false));return true;}if(code>=KeyEvent.KEYCODE_A&&code<=KeyEvent.KEYCODE_Z&&touchAllowed){send(json("type","key","key",String.valueOf((char)('A'+code-KeyEvent.KEYCODE_A)),"down",false));return true;}return super.onKeyUp(code,event);}
    }
}
