This is a modification of mrexodia's [smmserver](https://github.com/SmmServer/SmmServer)
that runs a docker container for a real Wii U to connect to. (outlined in [this issue](https://github.com/SmmServer/SmmServer/issues/54))

It is currently untested!

Requirements;
- A modded Wii U
- Any computer that can run docker (any OS)
- Some basic understanding of how to use a command prompt/terminal

This server will turn whatever computer you set this up on into a pretendo
DNS proxy server. This means that every time you open Super Mario
Maker 1, you will need this computer running as well as the docker
container. You can do this on your primary machine without issue, but
if you have a second computer laying around it might be better to use
that instead. This guide also assumes you're using Windows, but the
instructions are comparable to Linux/Mac as well.

The computer that you will need to use the local port 53, on Windows
it's something required by some Hyper-V services. We're going to disable
this and replace it. Follow [these instructions](https://learn.microsoft.com/en-us/answers/questions/3753205/solved-unable-to-stop-internet-connection-sharing?forum=windows-all&referrer=answers) to
disable these services.

First things first, you will need docker installed and running. Go do
[docker's website](https://docs.docker.com/engine/install/) and follow instructions for installing.

Next, open a command prompt. Type this command to ensure docker is
installed and running;

```
docker
```

You should get a long list of commands that can be run. If you get an
error, docker is not set up properly.

Next, get the image. Either place the [smmserver-docker-image.tar](https://github.com/jamieyello/smmserver-docker/releases/tag/untested) file as-is somewhere on
your computer (don't unzip it), open a command prompt/terminal in that folder
(on Windows, right click inside the folder in Explorer and click "Open in
Windows Terminal") and run

```
docker load -i smmserver-docker-image.tar
```

or build the image yourself by opening a command prompt/terminal in the folder of
this repository and running

```
docker build -t smmserver .
```

Then start it. `PUBLIC_IP` is the local IP of the computer running the
container (see the end of this guide for how to find it).

```
docker run -d --name smmserver -e PUBLIC_IP=192.168.x.x -v smmserver-data:/data -p53:53/udp -p53:53/tcp -p80:80 -p443:443 -p8000:8000 -p8383:8383 -p59900:59900/udp -p59921:59921/udp -p60000:60000/udp -p60021:60021/udp smmserver
```

In your browser, visit `localhost:8000`, and you should see a very simple
website, "Directory listing for /". If you see this site, congrats,
that's 90% of the hard part done.

Download all the files listed there (except README.txt) and put them all
in a temporary folder. Every file will
need to go into the Wii U system store, using a homebrew app. You can use [FTPiiU Everywhere](https://consolemods.org/wiki/WiiU:FTPiiU_Everywhere).

Put all files into your Wii U's `mlc01/sys/title/0005001b10054000/content/scerts/`

You will then need to modify you Wii U's connection settings. This is
done without homebrew. Go to
```
System Settings ->
    Internet ->
    Connect to the Internet ->
    (select active connection) ->
    Change Settings ->
    DNS ->
        (select Don't Auto-Obtain)
        Primary DNS: Local IP of your computer (192.168.x.x)*
        Secondary DNS: 1.1.1.1 (fallback to normal DNS server)
```

Save any changes.

*To get the local IP of your windows machine, run this command in a
command prompt;

```
ipconfig | find "IPv4" | find /V "192.168." | CLIP
```

Theoretically, all should be working. Open up Mario Maker 1 and see what
happens!
