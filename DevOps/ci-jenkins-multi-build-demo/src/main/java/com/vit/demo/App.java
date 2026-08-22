package com.vit.demo;

public class App {
    public static void main(String[] args) {
        System.out.println("Jenkins Continuous Integration demo is running.");
        System.out.println("2 + 3 = " + add(2, 3));
    }

    public static int add(int a, int b) {
        return a + b;
    }
}
