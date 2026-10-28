package ua.orbit.display;
import android.content.*;import android.database.Cursor;import android.net.Uri;import android.os.*;import java.io.*;
/** Exposes only the verified cached update, never arbitrary application files. */
public final class UpdateProvider extends ContentProvider {
    public boolean onCreate(){return true;}
    public String getType(Uri uri){return "application/vnd.android.package-archive";}
    public ParcelFileDescriptor openFile(Uri uri,String mode)throws FileNotFoundException {
        if(!"/update.apk".equals(uri.getPath())||!"r".equals(mode))throw new FileNotFoundException();
        return ParcelFileDescriptor.open(new File(getContext().getCacheDir(),"orbit-update.apk"),ParcelFileDescriptor.MODE_READ_ONLY);
    }
    public Cursor query(Uri u,String[]p,String s,String[]a,String o){return null;}
    public Uri insert(Uri u,ContentValues v){throw new UnsupportedOperationException();}
    public int delete(Uri u,String s,String[]a){throw new UnsupportedOperationException();}
    public int update(Uri u,ContentValues v,String s,String[]a){throw new UnsupportedOperationException();}
}
