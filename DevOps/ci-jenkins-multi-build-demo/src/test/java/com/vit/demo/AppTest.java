package com.vit.demo;

import org.junit.Test;
import static org.junit.Assert.fail;

public class AppTest {
    @Test
    public void testAdd() {
        int expected = 6;
        int actual = App.add(2, 3);
        if (expected == actual) {
            System.out.println("TEST PASSED: App.add(2, 3) returned " + actual + ".");
        } else {
            System.out.println("Test failed: expected " + expected + " but received " + actual);
            fail("Test failed: expected " + expected + " but received " + actual);
        }
    }
}
