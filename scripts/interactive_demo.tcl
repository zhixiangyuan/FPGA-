# UI thread consumes only the local controller's numeric simulation duration.
# Mailbox bytes are read by the testbench and driven through external DUT pins.
proc demo_poll {} {
    if {[file exists close.txt]} {quit -code 0 -force; return}
    if {[file exists zoom.txt]} {
        set f [open zoom.txt r]; set bounds [read $f]; close $f; file delete zoom.txt
        if {[llength $bounds] == 2} {
            lassign $bounds left right
            if {[string is integer -strict $left] && [string is integer -strict $right]} {
                catch {wave zoom range ${left}ns ${right}ns}
            }
        }
    }
    if {[file exists request.txt]} {
        set f [open request.txt r]; set ticks [string trim [read $f]]; close $f
        file delete request.txt
        if {![string is integer -strict $ticks] || $ticks < 1 || $ticks > 2000000000} {
            set f [open response.txt w]; puts $f "ERROR invalid duration"; close $f
        } elseif {[catch {run $ticks ns} problem]} {
            set f [open response.txt w]; puts $f "ERROR $problem"; close $f
        } else {
            set f [open response.txt w]; puts $f "DONE"; close $f
        }
    }
    after 200 demo_poll
}
after 200 demo_poll
echo "INTERACTIVE_READY: simulation stopped; use the Chinese control window."
