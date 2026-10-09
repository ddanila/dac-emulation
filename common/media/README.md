# Shared media

`media.h` provides borrowed byte-storage callbacks and explicit raw-sector geometry. Initialization validates image size and overflow; reads and writes check sector bounds and write policy. The memory adapter borrows its buffer. Owners retain responsibility for lifetime, closing, and persistence.

Controller commands stay in machine code. Juku geometry and deleted-sector metadata remain in its adapter; native file handling lives in `runners/native/juku_disk_file.c`.
