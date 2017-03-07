$(document).ready(function() {
    $("#next-button").click(function() {
        allow_exit();
        go_to_page("instructions/instruct-5");
    });
    $("#back-button").click(function() {
        allow_exit();
        go_to_page("instructions/instruct-2");
    });

    reqwest({
        url: "/experiment/p_move",
        method: 'get',
        success: function (resp) {
            p_move = resp.p_move;
            if (p_move <= 0) {
                $(".move-instruct").html("the treasure does not move, so it will always be where you found it last time.");
            } else {
                $(".move-instruct").html("the treasure will sometimes move locations so it might not be where you found it last time!");
            }
        }
    });
});