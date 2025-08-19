package juicesyo.github.ninechess;

import net.mamoe.mirai.contact.Contact;
import javax.imageio.ImageIO;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.regex.Pattern;

public class NineChess {
    public static InputStream inputStream;
    //public static int END = 0; //0:游戏进行中，1:分出胜负，2，死棋
    public static String stage = "chess"; //判断当前游戏阶段
    private static String msgStart;
    private static String msgEnd;

    private static final int height = 500;
    private static final int width = 500;
    private static final int EdgeRect = 50;
    private static final int MidRect = 110;
    private static final int InRect = 160;
    private static final int round = 50; //棋子大小

    private static BufferedImage X_Y_Axis;
    private static Graphics X_Y_Graphics;

    public static ArrayList<String> MyChess = new ArrayList<>();
    public static ArrayList<String> YourChess = new ArrayList<>();
    public static ArrayList<String> AllChess = new ArrayList<>();

    public static InputStream Main(Contact group,String msg,Integer id,Contact sender ) throws IOException {
        if (id == -1){
            Redraw();
        }else {

            msg = msg.replace("a","A").replace("b","B").replace("c","C");

            if (MyChess.size() <= 9 && YourChess.size() <= 9 && stage.equals("chess")) {
                int is; //1已存在流,0不存在
                try {
                    inputStream.available();
                    is = 1;
                } catch (Exception e) {
                    is = 0;
                    //System.out.println("InputStream Null.");
                }

                if (is == 0) {
                    Redraw();
                } else {
                    inputStream.reset();
                    X_Y_Axis = ImageIO.read(inputStream);
                    X_Y_Graphics = X_Y_Axis.getGraphics();
                }
                X_Y_Graphics.setColor(Color.BLACK);
                if (Inspect(msg, id)) {
                    if (id == 0) {
                        if(!MyChess.contains(msgStart + msgEnd)){
                            //i1要注意手动+1，规则类似（0,0+1）
                            X_Y_Graphics.fillRoundRect(ChessPieces(msgStart, msgEnd,1), ChessPieces(msgStart, msgEnd,2), round, round, round, round);
                            MyChess.add(msgStart + msgEnd);
                        }else {
                            group.sendMessage("你已经下过该位置。");
                            PluginMain.INSTANCE.setNext(sender.getId());
                        }
                    }
                    if(id == 1){
                        if (!YourChess.contains(msgStart + msgEnd)){
                            X_Y_Graphics.drawRoundRect(ChessPieces(msgStart, msgEnd,1), ChessPieces(msgStart, msgEnd,2), round, round, round, round);
                            YourChess.add(msgStart + msgEnd);
                        }else {
                            group.sendMessage("你已经下过该位置。");
                            PluginMain.INSTANCE.setNext(sender.getId());
                        }
                    }
                    if (MyChess.size() == 9 && YourChess.size() == 9 && !stage.equals("move")) {
                        stage = "move";
                        group.sendMessage("进入移动棋子阶段，请输入[A]-[B]来移动。");
                    }
                }else {
                    group.sendMessage("该位置不存在或已被占有。");
                    PluginMain.INSTANCE.setNext(sender.getId());
                }
            } else {
                try {
                    String past = msg.split("-")[0];
                    String now = msg.split("-")[1];
                    if (Inspect(now, id) && Inspect(past, id)) {
                        if (Inspect_Move(past,now)){
                            if (id == 0) {
                                if (MyChess.contains(past)) {
                                    for (int i = 0; i < MyChess.size(); i++) {
                                        if (past.equals(MyChess.get(i))) {
                                            MyChess.set(i, now);
                                        }
                                    }
                                }else {group.sendMessage(past+"没有你下过的棋子。"); PluginMain.INSTANCE.setNext(sender.getId());}
                            }
                            if (id == 1) {
                                if (YourChess.contains(past)) {
                                    for (int i = 0; i < YourChess.size(); i++) {
                                        if (past.equals(YourChess.get(i))) {
                                            YourChess.set(i, now);
                                        }
                                    }
                                }else {group.sendMessage(past+"没有你下过的棋子。"); PluginMain.INSTANCE.setNext(sender.getId());}
                            }

                            Redraw();

                            /*
                            * 整合所有棋子以便于重绘棋盘
                             */
                            if (!AllChess.isEmpty()){
                                AllChess.clear();
                            }
                            MyChess.addAll(YourChess);
                            AllChess.addAll(MyChess);
                            MyChess.removeAll(YourChess);


                            X_Y_Graphics.setColor(Color.BLACK);

                            for (String pieces : AllChess) {
                                msgStart = pieces.substring(0,1);
                                msgEnd = pieces.substring(1,2);
                                if (MyChess.contains(pieces)) {
                                    X_Y_Graphics.fillRoundRect(ChessPieces(msgStart, msgEnd,1), ChessPieces(msgStart, msgEnd,2), round, round, round, round);
                                }
                                if (YourChess.contains(pieces)) {
                                    X_Y_Graphics.drawRoundRect(ChessPieces(msgStart, msgEnd,1), ChessPieces(msgStart, msgEnd,2), round, round, round, round);
                                }
                            }
                        }else {
                            group.sendMessage("只能在横线上移动一个位置。");
                            PluginMain.INSTANCE.setNext(sender.getId());
                        }
                    } else {
                        group.sendMessage("有位置不存在或已被占有。");
                        PluginMain.INSTANCE.setNext(sender.getId());
                    }
                } catch (Exception e) {
                    group.sendMessage("参数错误。");
                    PluginMain.INSTANCE.setNext(sender.getId());
                }
            }
        }

        ByteArrayOutputStream byteArrayOutputStream = new ByteArrayOutputStream();
        ImageIO.write(X_Y_Axis,"png",byteArrayOutputStream);
        inputStream = new ByteArrayInputStream(byteArrayOutputStream.toByteArray());
        return inputStream;
    }

//绘制棋盘
    public static void Redraw(){
        X_Y_Axis = new BufferedImage(width, height, BufferedImage.TYPE_INT_BGR);
        X_Y_Graphics = X_Y_Axis.createGraphics();
        X_Y_Graphics.setColor(Color.white);
        X_Y_Graphics.fillRect(0, 0, width, height);
        X_Y_Graphics.setColor(Color.BLACK);
        //绘制棋盘
        //三个等距矩形
        X_Y_Graphics.drawRect(EdgeRect, EdgeRect, width - EdgeRect * 2, height - EdgeRect * 2);
        X_Y_Graphics.drawRect(MidRect, MidRect, width - MidRect * 2, height - MidRect * 2);
        X_Y_Graphics.drawRect(InRect, InRect, width - InRect * 2, height - InRect * 2);
        //四条线
        X_Y_Graphics.drawLine(width / 2, EdgeRect, width / 2, InRect);
        X_Y_Graphics.drawLine(EdgeRect, height / 2, InRect, height / 2);
        X_Y_Graphics.drawLine(width / 2, height - EdgeRect, width / 2, height - InRect);
        X_Y_Graphics.drawLine(width - EdgeRect, height / 2, width - InRect, height / 2);
    }

//检查落子位置是否有效，并赋值msgStart、msgStart
//type:site在MyChess时为0，site在YourChess时为1；主要用来判断棋子位置是否被对方占有
    public static boolean Inspect(String msg,int type){
        boolean result = false;
        if (msg.startsWith("A") || msg.startsWith("B")  || msg.startsWith("C")){
            msgStart = msg.substring(0, 1);
            msgEnd = msg.substring(1, 2);
            Pattern pattern = Pattern.compile("^[-\\+]?[\\d]*$");
            if (pattern.matcher(msgEnd).matches()) {
                if (Integer.parseInt(msgEnd) < 9 && Integer.parseInt(msgEnd) > 0) {
                    if (type == 0 && !YourChess.contains(msgStart + msgEnd)) {
                        result = true;
                    }
                    if (type == 1 && !MyChess.contains(msgStart + msgEnd)) {
                        result = true;
                    }
                }
            }
        }
       return result;
    }

//处理棋子落子位置，参数XY，1代表X，2代表Y
    public static int ChessPieces(String msgStart,String msgEnd,int XY){
        int result = -1;
        //24个点
        int[] Chess_Pieces_A =
                {
                        EdgeRect,EdgeRect, //A1(0,1)
                        width/2,EdgeRect, //A2(2,3)
                        width - EdgeRect,EdgeRect, //A3(4,5)
                        width - EdgeRect,height/2, //A4(6,7)
                        width - EdgeRect,height - EdgeRect, //A5(8,9)
                        width/2,height - EdgeRect, //A6(10,11)
                        EdgeRect,height - EdgeRect, //A7(12,13)
                        EdgeRect,height/2 //A8(14,15)

                };
        final int[] Chess_Pieces_B =
                {
                        MidRect, MidRect,
                        width / 2, MidRect,
                        width - MidRect, MidRect,
                        width - MidRect, height / 2,
                        width - MidRect, height - MidRect,
                        width / 2, height - MidRect,
                        MidRect, height - MidRect,
                        MidRect, height / 2
                };
        final int[] Chess_Pieces_C =
                {
                        InRect, InRect,
                        width / 2, InRect,
                        width - InRect, InRect,
                        width - InRect, height / 2,
                        width - InRect, height - InRect,
                        width / 2, height - InRect,
                        InRect, height - InRect,
                        InRect, height / 2
                };
        //Xn(2n-2,2n-1)
        if (msgStart.equals("A")) {
            if (XY==1) {
                result = Chess_Pieces_A[2 * Integer.parseInt(msgEnd) - 2] - round / 2;
            }
            if (XY==2){
                result = Chess_Pieces_A[2 * Integer.parseInt(msgEnd) - 1] - round / 2;
            }
        }
        if (msgStart.equals("B")){
            if (XY==1) {
                result = Chess_Pieces_B[2 * Integer.parseInt(msgEnd) - 2] - round / 2;
            }
            if (XY==2){
                result = Chess_Pieces_B[2 * Integer.parseInt(msgEnd) - 1] - round / 2;
            }
        }
        if (msgStart.equals("C")){
            if (XY==1) {
                result = Chess_Pieces_C[2 * Integer.parseInt(msgEnd) - 2] - round / 2;
            }
            if (XY==2){
                result = Chess_Pieces_C[2 * Integer.parseInt(msgEnd) - 1] - round / 2;
            }
        }
        return result;
    }

//判断棋子是否处于一条直线
    public static Boolean Straight_Line(int id){
        boolean result = false;
        String[] start = {"A","B","C"};
        String[] site =
                {
                        "1","2","3",
                        "3","4","5",
                        "5","6","7",
                        "7","8","1"
                };
        String[] _site =
                {
                        "A2","B2","C2",
                        "A4","B4","C4",
                        "A6","B6","C6",
                        "A8","B8","C8"
                };

        if (id==0){
            //Collections.sort(MyChess);
            if (MyChess.containsAll(Arrays.asList(_site[0],_site[1],_site[2]))||MyChess.containsAll(Arrays.asList(_site[3],_site[4],_site[5]))||MyChess.containsAll(Arrays.asList(_site[6],_site[7],_site[8]))||MyChess.containsAll(Arrays.asList(_site[9],_site[10],_site[11]))){
                result = true;
            }else {
                for (int i = 0; i <= 2; i++) {
                    for (int n = 1; n <= 4; n++) {
                        if (MyChess.containsAll(Arrays.asList(start[i] + site[3 * n - 3], start[i] + site[3 * n - 2], start[i] + site[3 * n - 1]))) {
                            result = true;
                        }
                    }
                }
            }
        }
        if (id==1){
            //Collections.sort(YourChess);
            if (YourChess.containsAll(Arrays.asList(_site[0],_site[1],_site[2]))||YourChess.containsAll(Arrays.asList(_site[3],_site[4],_site[5]))||YourChess.containsAll(Arrays.asList(_site[6],_site[7],_site[8]))||YourChess.containsAll(Arrays.asList(_site[9],_site[10],_site[11]))){
                result = true;
            }else {
                for (int i = 0; i <= 2; i++) {
                    for (int n = 1; n <= 4; n++) {
                        if (YourChess.containsAll(Arrays.asList(start[i] + site[3 * n - 3], start[i] + site[3 * n - 2], start[i] + site[3 * n - 1]))) {
                            result = true;
                        }
                    }
                }
            }
        }

        return result;
    }

//判断移动棋子是否可行
    public static Boolean Inspect_Move(String Past,String Now){
        boolean result = false;

        int Past_Site = Integer.parseInt(Past.substring(1,2));
        int Now_Site = Integer.parseInt(Now.substring(1,2));

        Past = Past.substring(0, 1);
        Now = Now.substring(0, 1);
        
        if(Past.equals(Now)) {
            if (Past_Site + 1 == Now_Site || Past_Site - 1 == Now_Site) {
                result = true;
            }else {
                if (Past_Site == 1 && Now_Site==8){
                    result = true;
                }
                if (Past_Site == 8 && Now_Site==1){
                    result = true;
                }
            }
        }else {
            Past = Past.replace("A","1").replace("C","1").replace("B","2");
            Now = Now.replace("A","1").replace("C","1").replace("B","2");

            if (Integer.parseInt(Past) + Integer.parseInt(Now) == 3){
                if (Past_Site == 2 && Now_Site == 2){
                    result = true;
                }
                if (Past_Site == 4 && Now_Site == 4){
                    result = true;
                }
                if (Past_Site == 6 && Now_Site == 6){
                    result = true;
                }
                if (Past_Site == 8 && Now_Site == 8){
                    result = true;
                }
            }
        }
        return result;
    }

    public static void Clean() throws IOException {
        MyChess.clear();
        YourChess.clear();
        AllChess.clear();
        inputStream.close();
        stage = "chess";
        PluginMain.INSTANCE.setNum(0);
        PluginMain.INSTANCE.setNext(null);
    }
}
