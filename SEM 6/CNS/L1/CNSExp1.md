Sahil Mahadik

CMPN-B

23102B0011

&nbsp;

**Experiment 1: Crack the Hash Challenge**

&nbsp;

1\. Objective

The objective of this challenge is to identify the plaintext password corresponding to a given hash using hash identification and cracking techniques.

&nbsp;

Task 1:



1.1 The Hash given:8bb6e862e54f2a795ffc4e541caed4d

First we identified the hash as MD5 then used a MD5 decryption tool to identify the plaintext as: **easy**.



1.2 Second Hash Given: CBFDAC6008F9CAB4083784CBD1874F76618D2A97 

I identified that it was a SHA–1 but used the hint and then used the decryption tool to find the plaintext as: **password123**.

&nbsp;

1.3 Third Hash Given was: 1C8BFE8F801D79745C4631D09FFF36C82AA37FC4CCE4FC946683D7B336B63032

Using the knowledge from the previous hint I figured this was an SHA and found that it was SHA-256 and used the decryption tool to identify the plaintext as: **letmein**.

&nbsp;

1.4 Forth Hash: $2y$12$Dwt1BZj6pcyc3Dy1FWZ5ieeUznr71EeNkJkUlypTsgbX1H68wsRom

I used the hint for this one which give me a link https://hashcat.net/wiki/doku.php?id=example\_hashes to identify what kind of hash it was and through the link I found that it was a **bcrypt $2\*$**, Blowfish (Unix) hash and to find the plaintext I used a tool called hashcat and a rockyou.txt file and filtered the txt file to only include four lowercase letter words as that was mentioned in the hint the command was hashcat -m 3200 hash.txt rockyou\_4.txt in the command line to find the plaintext as: **bleh**.



1.5 Fifth Hash: 279412f945939ba78ce0758d3fd83daa

I identified this hash as MD4 and used the decryption tool to find the plaintext as: Eternity22.

&nbsp;





Task 2:

2.1 Hash: F09EDCB1FCEFC6DFB23DC3505A882655FF77375ED8AA2D1C13F640FCCC2D0C85

As this was a SHA-256 I found the plaintext as: **paule**.

&nbsp;

2.2 Hash: 1DFECA0C002AE40B8619ECF94819CC1B

I identified the plaintext as: **n63umy8lkf4i**.

&nbsp;

2.3 Hash: $6$aReallyHardSalt$6WKUTqzq.UQQmrm0p/T7MPpMbGNnzXPMAXi4bJMl9be.cfi3/qxIf.hsGpS41BqMhSrHVXgMpdjS6xeKZAs02.

Salt: aReallyHardSalt

I identified this hash as sha512crypt $6$, SHA512 (Unix) 2 using the website of hashcat and used the hashcat tool and rockyou.txt unfiltered this time using the command hashcat -m 1800 hash.txt rockyou.txt to find the plaintext as: **waka99**.

&nbsp;

2.4 Hash: e5d8870e5bdd26602cab8dbe07a942c8669e56d6

Salt: tryhackme

Similarly for this one I identified the hash as HMAC-SHA1 and used the command hashcat -m 100 hash.txt rockyou.txt to find the plaintext as: **481616481618**.



